"""PRD 9.2: 운영자가 새 파일을 받을 때마다 더블클릭(또는 명령행)으로 실행하는 도구.

사용 예:
    python cli.py weekly-menu "C:\\식단표\\2026-07-20_주간식단표.xlsx" --week-start 2026-07-20
    python cli.py meal-log "C:\\취식기록\\transactions.xlsx" "C:\\맛평가\\taste_eval.xlsx"

meal-log는 식당취식정보(POS)와 맛평가 리스트, 두 파일을 함께 받아 사번/Knox ID +
날짜 + 식사구분 + 메뉴명으로 매칭해 합친 뒤 전송한다 (parsing/merge.py 참고).

미리보기(행 수, 경고)를 보여준 뒤 운영자가 확인(y)해야만 백엔드로 전송한다.
"""

import argparse
import datetime as dt
import sys
from collections import Counter

from config import load_config
from io_excel import read_used_range
from parsing.employee_mapping import load_employee_mapping
from parsing.meal_transaction_parser import parse_meal_transaction_grid
from parsing.merge import (
    _eval_key,
    diagnose_match_failure,
    diagnose_match_failure_by_evaluation,
    employee_key,
    merge_transactions_with_taste,
    sample_field_mismatches,
)
from parsing.taste_eval_parser import parse_taste_eval_grid
from parsing.weekly_menu_parser import parse_weekly_menu_grid
from upload import upload_meal_log, upload_weekly_menu


def _confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer == "y"


def _warn_if_ssl_disabled(verify_ssl: bool) -> None:
    if not verify_ssl:
        print("⚠️ SSL 인증서 검증이 비활성화된 상태로 전송합니다 (config.json의 verify_ssl=false).")


def _print_match_diagnosis(transactions, evaluations, employee_mapping) -> None:
    """복붙이 안 되는 환경에서도 숫자만 읽으면 원인을 좁힐 수 있는 자동 진단.

    조인 키 4개 필드(ID/날짜/식사구분/메뉴명) 중 하나씩 빼고 다시 세어, 어느
    필드가 매칭을 막고 있는지 알려준다. 맛평가 기준(정확) 진단을 먼저 보여주고,
    취식기록 기준(참고용, 부풀려질 수 있음) 진단을 보조로 보여준다.
    """
    by_eval = diagnose_match_failure_by_evaluation(transactions, evaluations, employee_mapping=employee_mapping)
    print("\n--- 진단 A: 맛평가 기준 (정확한 신호 — 이걸 우선 보세요) ---")
    print(f"  전체 맛평가: {by_eval['total_evaluations']}건")
    print(f"  전부 일치(현재 매칭 결과): {by_eval['full_match']}건")
    print(f"  ID만 무시하고 매칭: {by_eval['match_without_id']}건   <- 이게 높으면 ID(사번/Knox ID)가 원인")
    print(f"  날짜만 무시하고 매칭: {by_eval['match_without_date']}건   <- 이게 높으면 날짜가 원인")
    print(f"  식사구분만 무시하고 매칭: {by_eval['match_without_meal_type']}건   <- 이게 높으면 식사구분이 원인")
    print(f"  메뉴명만 무시하고 매칭: {by_eval['match_without_menu']}건   <- 이게 높으면 메뉴명이 원인")
    print("  (전부 일치가 낮은데 위 네 개도 다 낮으면, 여러 필드가 동시에 다른 것 — 아래 샘플을 봐야 함)")

    d = diagnose_match_failure(transactions, evaluations, employee_mapping=employee_mapping)
    print("\n--- 진단 B: 취식기록 기준 (참고용 — 인기메뉴 때문에 부풀려질 수 있음) ---")
    print(f"  전체 취식기록: {d['total_transactions']}행, 전체 맛평가: {d['total_evaluations']}행")
    print(f"  전부 일치(현재 매칭 결과): {d['full_match']}행")
    print(f"  ID만 무시하고 매칭: {d['match_without_id']}행")
    print(f"  날짜만 무시하고 매칭: {d['match_without_date']}행")
    print(f"  식사구분만 무시하고 매칭: {d['match_without_meal_type']}행")
    print(f"  메뉴명만 무시하고 매칭: {d['match_without_menu']}행")


def _print_field_mismatch_samples(transactions, evaluations, employee_mapping, n: int) -> None:
    """진단 A에서 어느 필드가 원인인지 좁혀진 뒤, 그 필드의 실제 값이 맛평가와
    취식기록 사이에 어떻게 다른지(공백, 자릿수, 매핑 누락 등) 나란히 보여준다.
    """
    samples = sample_field_mismatches(transactions, evaluations, employee_mapping=employee_mapping, n=n)
    labels = {"id": "ID(사번/Knox ID)", "date": "날짜", "menu": "메뉴명"}
    print(f"\n--- 진단 C: 필드별 값 비교 샘플 (필드당 최대 {n}건) ---")
    for field, label in labels.items():
        rows = samples[field]
        if not rows:
            print(f"  {label}: 값이 다른 샘플 없음")
            continue
        print(f"  {label}:")
        for eval_value, tx_value in rows:
            print(f"    맛평가={eval_value!r}  vs  취식기록={tx_value!r}")


def _print_debug_sample(transactions, evaluations, employee_mapping, n: int) -> None:
    """맛평가 매칭이 왜 안 되는지 원인을 못 찾을 때 쓰는 진단 출력.

    repr()로 출력해서 공백/타입 차이처럼 육안으로 "같아 보이는데" 실제로는 다른
    값을 그대로 드러낸다(예: "12345678" vs "12345678.0", 트레일링 공백 등).
    """
    print(f"\n--- 디버그: 취식기록 조인 키 샘플 (최대 {n}건) ---")
    for tx in transactions[:n]:
        key = _eval_key(
            employee_key(tx.employee_id, employee_mapping), tx.eaten_at.date(), tx.meal_type, tx.menu_display_name
        )
        print(f"  {key!r}")

    print(f"\n--- 디버그: 맛평가 조인 키 샘플 (최대 {n}건) ---")
    for ev in evaluations[:n]:
        key = _eval_key(ev.knox_id, ev.eaten_date, ev.meal_type, ev.menu_name)
        print(f"  {key!r}")
    print()


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
    _warn_if_ssl_disabled(config.verify_ssl)
    sent = upload_weekly_menu(
        rows,
        backend_base_url=config.backend_base_url,
        api_token=config.api_token,
        verify_ssl=config.verify_ssl,
    )
    print(f"✅ {sent}행 전송 완료")
    return 0


def _cmd_meal_log(args: argparse.Namespace) -> int:
    config = load_config()
    employee_mapping = load_employee_mapping(config.employee_mapping_path)

    transaction_grid = read_used_range(args.transaction_path, sheet_name=args.transaction_sheet)
    taste_grid = read_used_range(args.taste_path, sheet_name=args.taste_sheet)

    transactions = parse_meal_transaction_grid(transaction_grid)
    evaluations = parse_taste_eval_grid(taste_grid)
    rows = merge_transactions_with_taste(transactions, evaluations, employee_mapping=employee_mapping)

    if not rows:
        print("⚠️ 파싱된 행이 없습니다. 두 파일의 헤더 구조를 확인하세요.")
        return 1

    matched = sum(1 for r in rows if r.taste_score is not None)
    print(f"취식기록 {len(transactions)}행, 맛평가 {len(evaluations)}행 → 병합 {len(rows)}행")
    print(f"  맛평가와 매칭됨: {matched}행 ({matched / len(rows):.0%}) / 미평가: {len(rows) - matched}행")
    if employee_mapping:
        print(f"  사번↔Knox ID 매핑 {len(employee_mapping)}건 로드됨 ({config.employee_mapping_path})")
    print("샘플 5건:")
    for row in rows[:5]:
        print(f"  {row}")

    if args.debug_sample:
        _print_match_diagnosis(transactions, evaluations, employee_mapping)
        _print_field_mismatch_samples(transactions, evaluations, employee_mapping, args.debug_sample)
        _print_debug_sample(transactions, evaluations, employee_mapping, args.debug_sample)

    if not args.yes and not _confirm("백엔드로 전송할까요?"):
        print("전송을 취소했습니다.")
        return 0

    _warn_if_ssl_disabled(config.verify_ssl)
    sent = upload_meal_log(
        rows,
        backend_base_url=config.backend_base_url,
        api_token=config.api_token,
        verify_ssl=config.verify_ssl,
    )
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

    p_log = sub.add_parser("meal-log", help="식당취식정보 + 맛평가 리스트를 병합해 파싱/전송")
    p_log.add_argument("transaction_path", help="식당취식정보(POS) 엑셀 파일 경로")
    p_log.add_argument("taste_path", help="맛평가 리스트 엑셀 파일 경로")
    p_log.add_argument("--transaction-sheet", default=None, help="취식정보 시트 이름 (생략 시 첫 시트)")
    p_log.add_argument("--taste-sheet", default=None, help="맛평가 시트 이름 (생략 시 첫 시트)")
    p_log.add_argument("--yes", action="store_true", help="미리보기 확인 없이 바로 전송")
    p_log.add_argument(
        "--debug-sample",
        type=int,
        nargs="?",
        const=5,
        default=0,
        metavar="N",
        help="매칭이 잘 안 될 때 진단용 — 조인 키(사번/Knox ID, 날짜, 식사구분, 메뉴명) 샘플 N건을 그대로 출력 (기본 5)",
    )
    p_log.set_defaults(func=_cmd_meal_log)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
