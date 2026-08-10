"""PRD 7.1: 과거 강수 데이터를 daily_weather에 채워 넣는 운영 스크립트(2026-08).

사내망이 data.go.kr(공인 인터넷)에 못 닿을 수 있어(2026-08 확인), 이 스크립트는
두 가지 경로를 제공한다:

  csv      인터넷 되는 PC에서 만든 CSV(stat_date,precip_mm,avg_temp_c 헤더)를
           읽어 /ingest/weather-csv로 업로드한다. backend 서버와만 통신하면
           되므로 httpx만 있으면 어디서든 돌릴 수 있다(백엔드 앱 의존 없음).

  backfill 이 머신이 data.go.kr과 백엔드 DB 양쪽에 다 닿을 때만 쓴다 —
           app.services.weather_client.KmaWeatherClient로 실측 일자료를 가져와
           daily_corner_stats의 최초 날짜부터 어제까지 6개월 단위로 채운다.
           DB에 못 닿는 배포라면 대신 --out-csv로 CSV를 뽑아 위 csv 경로로
           올리는 두 단계로 나눠 쓴다.

사용 예:
  python scripts/import_weather_csv.py csv --backend-url https://internal.example.com \\
      --token "$INGEST_API_TOKEN" --file weather_2024_2026.csv

  python scripts/import_weather_csv.py backfill --out-csv weather_backfill.csv
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
    # 백엔드 앱 모듈은 이 서브커맨드에서만 필요하다 — csv 서브커맨드는 httpx만으로 동작한다.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from app.config import get_settings
    from app.db import SessionLocal
    from app.models.stats import DailyCornerStats, DailyWeather
    from app.services.weather_client import KmaWeatherClient

    db = SessionLocal()
    try:
        earliest = db.query(DailyCornerStats.stat_date).order_by(DailyCornerStats.stat_date.asc()).first()
        if earliest is None:
            print("daily_corner_stats에 데이터가 없어 백필 범위를 정할 수 없습니다.")
            return
        start = earliest[0]
        end = dt.date.today() - dt.timedelta(days=1)

        client = KmaWeatherClient(get_settings())
        if not client.is_configured:
            print("KMA_WEATHER_* 환경변수가 미설정 상태입니다 — backfill을 실행할 수 없습니다.")
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
                writer.writerow(["stat_date", "precip_mm", "avg_temp_c"])
                for rec in all_records:
                    writer.writerow([rec.stat_date.isoformat(), rec.precip_mm, rec.avg_temp_c])
            print(f"{args.out_csv}에 {len(all_records)}건 저장")

        if args.write_db:
            for rec in all_records:
                existing = db.get(DailyWeather, rec.stat_date)
                if existing:
                    existing.precip_mm = rec.precip_mm
                    existing.avg_temp_c = rec.avg_temp_c
                    existing.had_rain = rec.had_rain
                    existing.source = "kma_api"
                else:
                    db.add(
                        DailyWeather(
                            stat_date=rec.stat_date,
                            precip_mm=rec.precip_mm,
                            avg_temp_c=rec.avg_temp_c,
                            had_rain=rec.had_rain,
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
    csv_parser.add_argument("--file", required=True, help="stat_date,precip_mm,avg_temp_c 헤더의 CSV 경로")
    csv_parser.add_argument("--backend-url", required=True, help="예: https://internal.example.com")
    csv_parser.add_argument("--token", default=os.environ.get("INGEST_API_TOKEN", ""), help="INGEST_API_TOKEN")
    csv_parser.set_defaults(func=cmd_csv)

    backfill_parser = sub.add_parser("backfill", help="KMA API로 과거 전체 기간 백필(이 머신이 DB+data.go.kr 둘 다 닿을 때)")
    backfill_parser.add_argument("--out-csv", default=None, help="결과를 CSV로도 저장할 경로")
    backfill_parser.add_argument("--write-db", action="store_true", help="daily_weather에 직접 upsert")
    backfill_parser.set_defaults(func=cmd_backfill)

    args = parser.parse_args()
    if args.command == "csv" and not args.token:
        parser.error("--token 또는 INGEST_API_TOKEN 환경변수가 필요합니다.")
    args.func(args)


if __name__ == "__main__":
    main()
