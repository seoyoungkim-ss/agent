"""PRD 9.2: 운영자가 새 파일을 받을 때마다 더블클릭(또는 명령행)으로 실행하는 도구.

사용 예:
    python cli.py weekly-menu "C:\\식단표\\2026-07-20_주간식단표.xlsx" --week-start 2026-07-20
    python cli.py meal-log "C:\\취식로그\\mealdata.xlsx"

미리보기(행 수, 경고)를 보여준 뒤 운영자가 확인(y)해야만 백엔드로 전송한다.
"""

import argparse
import datetime as dt
import sys
from collections import Counter

from config import load_config
from io_excel import read_used_range
from parsing.meal_log_parser import parse_meal_log_grid
from parsing.weekly_menu_parser import parse_weekly_menu_grid
from upload import upload_meal_log, upload_weekly_menu


def _confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer == "y"


def _cmd_weekly_menu(args: argparse.Namespace) -> int:
    grid = read_used_range(args.path, sheet_name=args.sheet)
    week_start = dt.date.fromisoformat(args.week_start)
    rows = parse_weekly_menu_grid(grid, week_start)

    if not rows:
        print("⚠️ 파싱된 행이 없습니다. 시트/헤더 구조를 확인하세요.")
        return 1

    corners = Counter(r.corner_name for r in rows)
    meal_types = Counter(r.meal_type.value for r in rows)
    print(f"파싱 결과: 총 {len(rows)}행")
    print(f"  코너별 항목 수: {dict(corners)}")
    print(f"  식사구분별 항목 수: {dict(meal_types)}")
    print("샘플 5건:")
    for row in rows[:5]:
        print(f"  {row}")

    if not args.yes and not _confirm("백엔드로 전송할까요?"):
        print("전송을 취소했습니다.")
        return 0

    config = load_config()
    sent = upload_weekly_menu(rows, backend_base_url=config.backend_base_url, api_token=config.api_token)
    print(f"✅ {sent}행 전송 완료")
    return 0


def _cmd_meal_log(args: argparse.Namespace) -> int:
    grid = read_used_range(args.path, sheet_name=args.sheet)
    rows = parse_meal_log_grid(grid)

    if not rows:
        print("⚠️ 파싱된 행이 없습니다. 헤더 구조를 확인하세요.")
        return 1

    missing_comment = sum(1 for r in rows if not r.comment)
    missing_taste = sum(1 for r in rows if r.taste_score is None)
    print(f"파싱 결과: 총 {len(rows)}행")
    print(f"  주관식의견 없음: {missing_comment}행 / 맛평가 인식 실패: {missing_taste}행")
    print("샘플 5건:")
    for row in rows[:5]:
        print(f"  {row}")

    if not args.yes and not _confirm("백엔드로 전송할까요?"):
        print("전송을 취소했습니다.")
        return 0

    config = load_config()
    sent = upload_meal_log(rows, backend_base_url=config.backend_base_url, api_token=config.api_token)
    print(f"✅ {sent}행 전송 완료")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="카페테리아 데이터 수집 도구 (PRD 9.2)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_menu = sub.add_parser("weekly-menu", help="주간 식단표 xlsx 파싱/전송")
    p_menu.add_argument("path", help="주간 식단표 엑셀 파일 경로")
    p_menu.add_argument("--week-start", required=True, help="이 표가 나타내는 주의 월요일 날짜 (YYYY-MM-DD)")
    p_menu.add_argument("--sheet", default=None, help="시트 이름 (생략 시 첫 시트)")
    p_menu.add_argument("--yes", action="store_true", help="미리보기 확인 없이 바로 전송")
    p_menu.set_defaults(func=_cmd_weekly_menu)

    p_log = sub.add_parser("meal-log", help="취식 로그(mealdata) 파싱/전송")
    p_log.add_argument("path", help="취식 로그 엑셀 파일 경로")
    p_log.add_argument("--sheet", default=None, help="시트 이름 (생략 시 첫 시트)")
    p_log.add_argument("--yes", action="store_true", help="미리보기 확인 없이 바로 전송")
    p_log.set_defaults(func=_cmd_meal_log)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
