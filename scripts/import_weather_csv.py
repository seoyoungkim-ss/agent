"""PRD 7.1: 과거 강수 데이터를 daily_weather에 채워 넣는 운영 스크립트(2026-08).

사내망이 data.go.kr(공인 인터넷)에 못 닿을 수 있어(2026-08 확인), 이 스크립트는
두 가지 경로를 제공한다:

  csv      인터넷 되는 PC에서 만든 CSV(stat_date,precip_mm,avg_temp_c,snow_cm,
           max_temp_c,min_temp_c 헤더 — 뒤 3개는 §71 폭설/폭염/한파 분류용,
           없으면 빈 칸으로 둬도 됨)를 읽어 /ingest/weather-csv로 업로드한다.
           backend 서버와만 통신하면 되므로 httpx만 있으면 어디서든 돌릴 수
           있다(백엔드 앱 의존 없음).

  backfill data.go.kr에서 실측 일자료를 가져온다. --start-date를 주면 DB 접속이
           전혀 필요 없다(2026-08 수정 — 예전엔 --out-csv 전용으로 써도 시작일을
           daily_corner_stats에서 찾으려고 무조건 DB에 접속했다). --write-db를
           켜면 daily_weather에 직접 upsert하므로 그때만 DB 접속이 필요하다.
           DB에 못 닿는 배포라면 --out-csv로 CSV를 뽑아 csv 경로로 올리는
           두 단계로 나눠 쓴다.

사용 예:
  # ⚠️ --backend-url엔 반드시 /api까지 포함해야 한다 — 이 앱의 API는 전부
  # /api 아래 마운트돼 있고(main.py: api_router = APIRouter(prefix="/api")),
  # ingestion-tool의 backend_base_url 관례와도 동일하다. /api를 빼먹으면
  # 404가 나야 정상인데, frontend_dist_dir가 존재하는 배포에서는 SPA
  # 정적파일 폴백(main.py의 StaticFiles(html=True) 마운트)에 걸려 에러 없이
  # 조용히 실패할 수 있다(2026-08 실사용 확인) — 반드시 /api 포함.
  python scripts/import_weather_csv.py csv --backend-url https://internal.example.com/api \\
      --token "$INGEST_API_TOKEN" --file weather_2024_2026.csv

  # DB 접속 없이 CSV만 뽑기 (시작일 직접 지정)
  python scripts/import_weather_csv.py backfill --start-date 2026-01-01 --out-csv weather_backfill.csv

  # 이 머신이 DB에도 닿을 때 — 시작일을 daily_corner_stats에서 자동 추정 + 바로 반영
  python scripts/import_weather_csv.py backfill --write-db
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import os
import sys
from pathlib import Path

import httpx

_BATCH_SIZE = 500
_BACKFILL_CHUNK_DAYS = 180  # data.go.kr numOfRows 상한을 넘지 않도록 6개월 단위로 쪼갠다


def _read_csv_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(
                {
                    "stat_date": row["stat_date"],
                    "precip_mm": float(row["precip_mm"]) if row.get("precip_mm") else None,
                    "avg_temp_c": float(row["avg_temp_c"]) if row.get("avg_temp_c") else None,
                    # §71: 폭설/폭염/한파 분류용 — 구버전 CSV(이 3개 컬럼 없음)도
                    # row.get()이 None을 주므로 그대로 하위호환된다.
                    "snow_cm": float(row["snow_cm"]) if row.get("snow_cm") else None,
                    "max_temp_c": float(row["max_temp_c"]) if row.get("max_temp_c") else None,
                    "min_temp_c": float(row["min_temp_c"]) if row.get("min_temp_c") else None,
                }
            )
    return rows


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def cmd_csv(args: argparse.Namespace) -> None:
    rows = _read_csv_rows(Path(args.file))
    if not rows:
        print("CSV에 행이 없습니다.")
        return

    url = f"{args.backend_url.rstrip('/')}/ingest/weather-csv"
    headers = {"Authorization": f"Bearer {args.token}"}
    total_upserted = 0
    with httpx.Client(headers=headers, timeout=30.0) as client:
        for batch in _chunks(rows, _BATCH_SIZE):
            resp = client.post(url, json={"rows": batch})
            resp.raise_for_status()
            total_upserted += resp.json().get("upserted", 0)
    print(f"업로드 완료: {len(rows)}건 중 {total_upserted}건 upsert")


def cmd_backfill(args: argparse.Namespace) -> None:
    # 백엔드 앱 모듈(설정 읽기·API 클라이언트)은 이 서브커맨드에서만 필요하다 —
    # csv 서브커맨드는 httpx만으로 동작한다. DB 접속은 --write-db를 켰을 때나
    # --start-date를 안 줘서 daily_corner_stats로 범위를 추정해야 할 때만 연다
    # (2026-08 버그 수정: 예전엔 --out-csv 전용으로 써도 시작일을 정하려고
    # 무조건 DB에 접속해서, DB에 못 닿는 배포에서 이 옵션 자체가 못 쓰였다).
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from app.config import get_settings
    from app.services.weather_client import KmaWeatherClient

    client = KmaWeatherClient(get_settings())
    if not client.is_configured:
        print("KMA_WEATHER_* 환경변수가 미설정 상태입니다 — backfill을 실행할 수 없습니다.")
        return

    end = dt.date.fromisoformat(args.end_date) if args.end_date else dt.date.today() - dt.timedelta(days=1)

    if args.start_date:
        start = dt.date.fromisoformat(args.start_date)
    elif args.write_db:
        # DB에 어차피 접속하니(upsert 대상) 편의상 daily_corner_stats 최초 날짜로 추정한다.
        from app.db import SessionLocal
        from app.models.stats import DailyCornerStats

        db = SessionLocal()
        try:
            earliest = db.query(DailyCornerStats.stat_date).order_by(DailyCornerStats.stat_date.asc()).first()
        finally:
            db.close()
        if earliest is None:
            print("daily_corner_stats에 데이터가 없어 백필 범위를 정할 수 없습니다 — --start-date로 직접 지정하세요.")
            return
        start = earliest[0]
    else:
        print("--start-date를 지정하세요 (DB 접속 없이 --out-csv만 쓸 때는 시작일을 자동으로 못 정합니다).")
        return

    all_records = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + dt.timedelta(days=_BACKFILL_CHUNK_DAYS - 1), end)
        records = asyncio.run(client.fetch_daily_range(cursor, chunk_end))
        all_records.extend(records)
        print(f"{cursor} ~ {chunk_end}: {len(records)}건 조회")
        cursor = chunk_end + dt.timedelta(days=1)

    if args.out_csv:
        with open(args.out_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["stat_date", "precip_mm", "avg_temp_c", "snow_cm", "max_temp_c", "min_temp_c"])
            for rec in all_records:
                writer.writerow(
                    [
                        rec.stat_date.isoformat(),
                        rec.precip_mm,
                        rec.avg_temp_c,
                        rec.snow_cm,
                        rec.max_temp_c,
                        rec.min_temp_c,
                    ]
                )
        print(f"{args.out_csv}에 {len(all_records)}건 저장")

    if args.write_db:
        from app.db import SessionLocal
        from app.models.stats import DailyWeather

        db = SessionLocal()
        try:
            for rec in all_records:
                existing = db.get(DailyWeather, rec.stat_date)
                if existing:
                    existing.precip_mm = rec.precip_mm
                    existing.avg_temp_c = rec.avg_temp_c
                    existing.had_rain = rec.had_rain
                    existing.snow_cm = rec.snow_cm
                    existing.max_temp_c = rec.max_temp_c
                    existing.min_temp_c = rec.min_temp_c
                    existing.source = "kma_api"
                else:
                    db.add(
                        DailyWeather(
                            stat_date=rec.stat_date,
                            precip_mm=rec.precip_mm,
                            avg_temp_c=rec.avg_temp_c,
                            had_rain=rec.had_rain,
                            snow_cm=rec.snow_cm,
                            max_temp_c=rec.max_temp_c,
                            min_temp_c=rec.min_temp_c,
                            source="kma_api",
                        )
                    )
            db.commit()
            print(f"DB에 {len(all_records)}건 upsert 완료")
        finally:
            db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    csv_parser = sub.add_parser("csv", help="로컬 CSV를 /ingest/weather-csv로 업로드")
    csv_parser.add_argument(
        "--file", required=True, help="stat_date,precip_mm,avg_temp_c[,snow_cm,max_temp_c,min_temp_c] 헤더의 CSV 경로"
    )
    csv_parser.add_argument("--backend-url", required=True, help="예: https://internal.example.com")
    csv_parser.add_argument("--token", default=os.environ.get("INGEST_API_TOKEN", ""), help="INGEST_API_TOKEN")
    csv_parser.set_defaults(func=cmd_csv)

    backfill_parser = sub.add_parser(
        "backfill", help="KMA API로 과거 기간 백필 (--out-csv만 쓰면 DB 접속 불필요)"
    )
    backfill_parser.add_argument("--out-csv", default=None, help="결과를 CSV로도 저장할 경로")
    backfill_parser.add_argument("--write-db", action="store_true", help="daily_weather에 직접 upsert (DB 접속 필요)")
    backfill_parser.add_argument(
        "--start-date", default=None, help="백필 시작일(YYYY-MM-DD). 안 주면 --write-db일 때만 DB에서 추정"
    )
    backfill_parser.add_argument("--end-date", default=None, help="백필 종료일(YYYY-MM-DD). 기본값: 어제")
    backfill_parser.set_defaults(func=cmd_backfill)

    args = parser.parse_args()
    if args.command == "csv" and not args.token:
        parser.error("--token 또는 INGEST_API_TOKEN 환경변수가 필요합니다.")
    args.func(args)


if __name__ == "__main__":
    main()
