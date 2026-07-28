"""식당취식정보(POS) + 맛평가 리스트를 하나의 meal_log 행으로 합친다.

⚠️ 확인 필요한 가정 (실제 데이터로 검증 전까지):
  1. 맛평가의 Knox ID == 취식기록의 사원번호라고 가정한다. 실제로 서로 다른 ID
     체계라면(예: Knox ID가 계정명, 사원번호가 사번) 별도 매핑 테이블이 필요하다 —
     그 경우 이 파일의 employee_key()만 교체하면 된다.
  2. 맛평가의 메뉴명은 취식기록의 "화면표시명(한글)"과 매칭한다고 가정한다
     ("메뉴명"(코드성 이름)이 아니라).
  3. 조인 키는 (사번, 취식 날짜, 식사구분, 메뉴명) 조합이다. 맛평가에 시간 정보가
     없어서(날짜만) 시(時)까지는 못 맞춘다 — 같은 사람이 같은 날 같은 식사구분에
     같은 메뉴를 두 번 이상 먹는 경우는 구분하지 못한다(드문 경우로 가정).
"""

from collections import defaultdict

from models import ParsedMealLogRow, ParsedMealTransactionRow, ParsedTasteEvalRow


def _normalize_menu(name: str) -> str:
    return name.strip()


def employee_key(transaction_employee_id: str) -> str:
    """맛평가의 knox_id와 비교할 수 있는 형태로 정규화. 현재는 그대로 반환 —
    실제로 ID 체계가 다르면 여기서 변환/매핑 테이블 조회를 추가한다."""
    return transaction_employee_id.strip()


def _eval_key(knox_id: str, eaten_date, meal_type, menu_name: str) -> tuple:
    return (knox_id.strip(), eaten_date, meal_type, _normalize_menu(menu_name))


def merge_transactions_with_taste(
    transactions: list[ParsedMealTransactionRow],
    evaluations: list[ParsedTasteEvalRow],
    *,
    only_normal_status: bool = True,
) -> list[ParsedMealLogRow]:
    eval_index: dict[tuple, ParsedTasteEvalRow] = {}
    duplicate_keys: set[tuple] = set()
    for ev in evaluations:
        key = _eval_key(ev.knox_id, ev.eaten_date, ev.meal_type, ev.menu_name)
        if key in eval_index:
            duplicate_keys.add(key)  # 같은 키로 평가가 2건 이상 — 마지막 값 사용, 경고 목적으로만 기록
        eval_index[key] = ev

    merged: list[ParsedMealLogRow] = []
    for tx in transactions:
        if only_normal_status and tx.status and tx.status != "정상":
            continue

        key = _eval_key(
            employee_key(tx.employee_id), tx.eaten_at.date(), tx.meal_type, tx.menu_display_name
        )
        evaluation = eval_index.get(key)

        merged.append(
            ParsedMealLogRow(
                eaten_at=tx.eaten_at,
                employee_id=tx.employee_id,
                meal_type=tx.meal_type,
                corner_name=tx.corner_name,
                menu_name=_normalize_menu(tx.menu_display_name) or tx.menu_code_name or None,
                taste_score=evaluation.taste_score if evaluation else None,
                comment=evaluation.comment if evaluation else None,
            )
        )
    return merged
