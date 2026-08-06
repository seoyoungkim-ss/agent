"""PRD 9.2: 운영자가 새 파일을 받을 때마다 더블클릭(또는 명령행)으로 실행하는 도구.

사용 예:
    python cli.py weekly-menu "C:\\식단표\\2026-07-20_주간식단표.xlsx"
    python cli.py weekly-menu-batch "C:\\식단표" --dry-run
    python cli.py meal-log "C:\\취식기록\\transactions.xlsx" "C:\\맛평가\\taste_eval.xlsx"

주간 식단표는 어느 주인지를 **시트 헤더의 날짜에서 자동으로 알아낸다** — 운영자가
--week-start를 손으로 계산할 필요가 없다. 인식된 주는 전송 전에 항상 표시되고,
확신이 없으면 값을 만들어내지 않고 실패한다(그때만 --week-start로 지정).

weekly-menu-batch는 폴더를 통째로 올릴 때 쓴다. Excel 인스턴스를 하나만 띄우고,
같은 주가 이미 있으면 교체하므로 **여러 번 돌려도 중복이 쌓이지 않는다.**
처음엔 --dry-run으로 파일→주 매핑부터 확인하는 걸 권한다.

meal-log는 식당취식정보(POS)와 맛평가 리스트, 두 파일을 함께 받아 사번/Knox ID +
날짜 + 식사구분 + 메뉴명으로 매칭해 합친 뒤 전송한다 (parsing/merge.py 참고).

미리보기(행 수, 경고)를 보여준 뒤 운영자가 확인(y)해야만 백엔드로 전송한다.
"""

import argparse
import datetime as dt
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from config import load_config
from io_excel import excel_session, read_used_range
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
from parsing.weekly_menu_parser import (
    WeeklyMenuParseError,
    infer_week_start,
    parse_weekly_menu_grid,
)
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


def _resolve_week_start(grid, explicit: str | None) -> tuple[dt.date, str]:
    """(주 시작일, 어떻게 정해졌는지 설명). 운영자가 준 값이 항상 이긴다.

    설명 문자열을 함께 돌려주는 이유: 자동 추론이 틀리면 그 주 편성이 통째로
    어긋나므로, 화면에 "추론"인지 "지정"인지가 보여야 한다.
    """
    if explicit:
        return dt.date.fromisoformat(explicit), "운영자 지정"
    return infer_week_start(grid), "시트 헤더에서 자동 인식"


def _cmd_weekly_menu(args: argparse.Namespace) -> int:
    grid = read_used_range(args.path, sheet_name=args.sheet)
    try:
        week_start, how = _resolve_week_start(grid, args.week_start)
    except WeeklyMenuParseError as exc:
        print(f"⚠️ 주 시작일을 알 수 없습니다: {exc}")
        return 1
    rows = parse_weekly_menu_grid(grid, week_start)

    if not rows:
        print("⚠️ 파싱된 행이 없습니다. 시트/헤더 구조를 확인하세요.")
        return 1

    corners = Counter(r.corner_name for r in rows)
    meal_types = Counter(r.meal_type.value for r in rows)
    print(f"대상 주: {week_start.isoformat()}(월) ~ {(week_start + dt.timedelta(days=5)).isoformat()}(토)  [{how}]")
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
        replace_existing=args.replace_existing,
    )
    print(f"✅ {sent}행 전송 완료")
    return 0


# ---------------------------------------------------------------------------
# 일괄 적재
# ---------------------------------------------------------------------------

_MENU_FILE_SUFFIXES = (".xlsx", ".xlsm", ".xls")


def _pad(text: str, width: int) -> str:
    """한글 파일명이 섞여도 열이 맞게 채운다.

    한글·한자는 터미널에서 두 칸을 차지하는데 파이썬 문자열 포맷은 글자 수로
    세기 때문에, 그냥 f"{name:<44}"로 하면 표가 어긋난다. 이 표가 잘못된 주로
    적재하는 걸 막는 마지막 확인 수단이라 읽기 쉬워야 한다.
    """
    display = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(1, width - display)


def _collect_menu_files(directory: Path, recursive: bool) -> list[Path]:
    """폴더에서 식단표 후보 파일을 정렬해 모은다.

    `~$`로 시작하는 파일은 뺀다 — 엑셀이 파일을 열어둘 때 만드는 잠금 파일이고,
    파싱하면 깨진다. 운영자가 식단표를 열어둔 채 배치를 돌리는 건 흔한 일이다.
    """
    paths = directory.rglob("*") if recursive else directory.glob("*")
    return sorted(
        p
        for p in paths
        if p.is_file() and p.suffix.lower() in _MENU_FILE_SUFFIXES and not p.name.startswith("~$")
    )


def _cmd_weekly_menu_batch(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"⚠️ 폴더가 아닙니다: {directory}")
        return 1

    files = _collect_menu_files(directory, args.recursive)
    if not files:
        print(f"⚠️ {directory}에 식단표 파일(.xlsx/.xlsm/.xls)이 없습니다.")
        return 1

    print(f"{len(files)}개 파일을 읽습니다 — Excel 인스턴스 1개를 재사용합니다.\n")
    parsed: list[tuple[Path, dt.date, list]] = []
    skipped: list[tuple[Path, str]] = []

    with excel_session() as app:
        for path in files:
            try:
                grid = read_used_range(str(path), sheet_name=args.sheet, app=app)
                week_start = infer_week_start(grid)
                rows = parse_weekly_menu_grid(grid, week_start)
            except Exception as exc:  # 한 파일이 이상해도 나머지는 계속 간다
                skipped.append((path, str(exc)))
                print(f"  ⚠️ {path.name}: {exc}")
                continue
            if not rows:
                skipped.append((path, "파싱된 행이 없음"))
                print(f"  ⚠️ {path.name}: 파싱된 행이 없습니다")
                continue
            parsed.append((path, week_start, rows))
            print(f"  ✓ {path.name}")

    # 업로드 전 마지막 방어선 — 주 매핑이 틀리면 여기서 눈으로 잡아야 한다.
    print(f"\n--- 파일별 인식 결과 ({len(parsed)}개) ---")
    print(f"{_pad('파일명', 46)}{_pad('주 시작(월)', 14)}{_pad('~ 토(끝)', 14)}행수")
    for path, week_start, rows in parsed:
        end = week_start + dt.timedelta(days=5)
        print(f"{_pad(path.name, 46)}{_pad(week_start.isoformat(), 14)}{_pad(end.isoformat(), 14)}{len(rows)}")

    weeks = [w for _, w, _ in parsed]
    duplicates = sorted({w for w in weeks if weeks.count(w) > 1})
    if duplicates:
        # 같은 주가 두 번 나오면 슬롯 교체 특성상 나중 파일이 앞 파일을 덮는다.
        print(f"\n⚠️ 같은 주를 가리키는 파일이 여러 개입니다: {[w.isoformat() for w in duplicates]}")
        print("   나중 파일이 앞 파일을 덮어씁니다 — 의도한 게 맞는지 확인하세요.")
    if skipped:
        print(f"\n⚠️ 건너뛴 파일 {len(skipped)}개:")
        for path, reason in skipped:
            print(f"   {path.name} — {reason}")

    total_rows = sum(len(rows) for _, _, rows in parsed)
    print(f"\n합계: {len(parsed)}개 파일 / {total_rows}행")

    if args.dry_run:
        print("\n[dry-run] 아무것도 전송하지 않았습니다. 위 표의 주 매핑이 맞으면 --dry-run 없이 다시 실행하세요.")
        return 0
    if not parsed:
        print("\n전송할 파일이 없습니다.")
        return 1

    print("\n⚠️ 위 주에 이미 적재된 식단표가 있으면 **교체**됩니다.")
    print("   (화면에서 직접 고친 주찬/부찬·건강가든 행은 그대로 보존됩니다)")
    if not args.yes and not _confirm("백엔드로 전송할까요?"):
        print("전송을 취소했습니다.")
        return 0

    config = load_config()
    _warn_if_ssl_disabled(config.verify_ssl)

    sent_total = 0
    failed: list[tuple[Path, str]] = []
    for path, week_start, rows in parsed:
        # 파일 단위로 보낸다 — 중간에 실패해도 어느 주가 안 올라갔는지 바로 안다.
        try:
            sent = upload_weekly_menu(
                rows,
                backend_base_url=config.backend_base_url,
                api_token=config.api_token,
                verify_ssl=config.verify_ssl,
                replace_existing=True,
            )
        except Exception as exc:
            failed.append((path, str(exc)))
            print(f"  ❌ {path.name} ({week_start.isoformat()} 주): {exc}")
            continue
        sent_total += sent
        print(f"  ✅ {path.name} ({week_start.isoformat()} 주) {sent}행")

    print(f"\n전송 완료 {len(parsed) - len(failed)}개 파일 / {sent_total}행")
    if skipped:
        print(f"건너뜀 {len(skipped)}개 (위 목록 참고)")
    if failed:
        print(f"❌ 실패 {len(failed)}개 — 고친 뒤 그 파일만 다시 올리면 됩니다(교체 방식이라 중복되지 않습니다)")
        return 1
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

    p_menu = sub.add_parser("weekly-menu", help="주간 식단표 xlsx 파싱/전송 (파일 1개)")
    p_menu.add_argument("path", help="주간 식단표 엑셀 파일 경로")
    p_menu.add_argument(
        "--week-start",
        default=None,
        help="이 표가 나타내는 주의 월요일 날짜 (YYYY-MM-DD). "
        "생략하면 시트 헤더의 날짜에서 자동 인식하고, 인식 결과를 전송 전에 보여준다.",
    )
    p_menu.add_argument("--sheet", default=None, help="시트 이름 (생략 시 첫 시트)")
    p_menu.add_argument("--yes", action="store_true", help="미리보기 확인 없이 바로 전송")
    p_menu.add_argument(
        "--replace-existing",
        action="store_true",
        help="같은 주를 다시 올릴 때 기존 행을 교체 (관리자가 화면에서 고친 행은 보존). "
        "안 주면 그대로 덧붙으므로 중복이 쌓인다.",
    )
    p_menu.set_defaults(func=_cmd_weekly_menu)

    p_batch = sub.add_parser(
        "weekly-menu-batch",
        help="폴더 안의 주간 식단표를 한 번에 파싱/전송 (주차는 시트 헤더에서 자동 인식)",
    )
    p_batch.add_argument("directory", help="주간 식단표 엑셀 파일들이 있는 폴더")
    p_batch.add_argument("--recursive", action="store_true", help="하위 폴더까지 훑기")
    p_batch.add_argument("--sheet", default=None, help="시트 이름 (생략 시 첫 시트)")
    p_batch.add_argument(
        "--dry-run",
        action="store_true",
        help="전송하지 않고 파일별 인식 결과(어느 주로 읽혔는지)만 보여준다. 처음엔 이걸로 확인하세요.",
    )
    p_batch.add_argument("--yes", action="store_true", help="확인 없이 바로 전송")
    p_batch.set_defaults(func=_cmd_weekly_menu_batch)

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
