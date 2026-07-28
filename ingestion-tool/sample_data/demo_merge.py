"""sample_data의 합성 엑셀 2개를 실제 파서+병합 로직으로 돌려보는 데모.

실제 운영에서는 io_excel.py(xlwings)가 그리드를 만들지만, 이 합성 파일은 DRM이
없는 테스트용이라 openpyxl로도 똑같은 모양의 그리드를 만들 수 있다 — 그래서
xlwings/Excel 없이 이 Linux 환경에서도 파싱 로직 전체를 검증할 수 있다.

실행: python sample_data/demo_merge.py
"""

import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent.parent))

from parsing.meal_transaction_parser import parse_meal_transaction_grid
from parsing.merge import merge_transactions_with_taste
from parsing.taste_eval_parser import parse_taste_eval_grid

OUT_DIR = Path(__file__).parent


def read_grid(path: Path) -> list[list]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    return [list(row) for row in ws.iter_rows(values_only=True)]


def main() -> None:
    transaction_grid = read_grid(OUT_DIR / "sample_transactions.xlsx")
    taste_grid = read_grid(OUT_DIR / "sample_taste_eval.xlsx")

    transactions = parse_meal_transaction_grid(transaction_grid)
    evaluations = parse_taste_eval_grid(taste_grid)
    merged = merge_transactions_with_taste(transactions, evaluations)

    print(f"취식기록 파싱: {len(transactions)}행 (원본 4+1행 중 사원번호 빈 3행은 skip)")
    print(f"맛평가 파싱: {len(evaluations)}행 (원본 12+1행 중 Knox ID 빈 11행은 skip)")
    print(f"병합 결과: {len(merged)}행\n")

    for row in merged:
        matched = "✅ 매칭됨" if row.taste_score else "— 미평가"
        print(
            f"{matched} | {row.eaten_at} | {row.employee_id} | {row.meal_type.value} | "
            f"{row.corner_name} | 메뉴={row.menu_name} | 평가={row.taste_score} | "
            f"코멘트={row.comment}"
        )


if __name__ == "__main__":
    main()
