"""식당취식정보(POS) + 맛평가 리스트를 하나의 meal_log 행으로 합친다.

확인된 사실 / 남은 가정:
  1. ✅ **Knox ID == 사원번호로 직접 비교 가능한 건 A사 인원뿐**이다(사용자 확인).
     B/C/D사·기타 인원은 두 값 체계가 다르므로 이 문자열 비교로는 애초에 안 맞는다 —
     그런 행은 맛평가와 매칭이 안 돼서 "미평가"로 남는 게 **버그가 아니라 정상**이다.
     A사 외 인원의 Knox ID 매핑 방법이 별도로 생기면 employee_key()에 회사구분별
     분기(또는 매핑 테이블 조회)를 추가하면 된다.
  2. ⚠️ 맛평가의 메뉴명은 취식기록의 "화면표시명(한글)"과 매칭한다고 가정한다
     ("메뉴명"(코드성 이름)이 아니라) — 아직 실물로 재검증 전.
  3. ⚠️ 조인 키는 (사번, 취식 날짜, 식사구분, 메뉴명) 조합이다. 맛평가에 시간 정보가
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
