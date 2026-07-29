"""식당취식정보(POS) + 맛평가 리스트를 하나의 meal_log 행으로 합친다.

확인된 사실 / 남은 가정:
  1. ✅ **Knox ID == 사원번호로 직접 비교 가능한 건 A사 인원뿐**이다(사용자 확인).
     B/C/D사·기타 인원은 두 값 체계가 다르므로 이 문자열 비교로는 애초에 안 맞는다.
     이 경우를 위해 `employee_mapping.py`로 로드한 사번→knox_id 매핑을
     `merge_transactions_with_taste(..., employee_mapping=...)`으로 넘기면 된다 —
     매핑에 없는 사번은 그대로 두므로(원래 A사 동작과 동일), 매핑 파일이 없거나
     불완전해도 매칭 실패가 "미평가"로 조용히 남을 뿐 에러가 나지 않는다.
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


def employee_key(transaction_employee_id: str, mapping: dict[str, str] | None = None) -> str:
    """맛평가의 knox_id와 비교할 수 있는 형태로 정규화.

    A사 인원은 사번==knox_id라 매핑 없이도 일치한다. mapping(사번→knox_id)이
    주어지고 그 사번이 매핑에 있으면 knox_id로 변환해 비교하고, 없으면 사번을
    그대로 반환한다(매칭 안 되면 "미평가"로 남을 뿐 — 정상 동작).
    """
    employee_id = transaction_employee_id.strip()
    if mapping and employee_id in mapping:
        return mapping[employee_id]
    return employee_id


def _eval_key(knox_id: str, eaten_date, meal_type, menu_name: str) -> tuple:
    return (knox_id.strip(), eaten_date, meal_type, _normalize_menu(menu_name))


def diagnose_match_failure(
    transactions: list[ParsedMealTransactionRow],
    evaluations: list[ParsedTasteEvalRow],
    *,
    employee_mapping: dict[str, str] | None = None,
) -> dict[str, int]:
    """맛평가 매칭률이 낮을 때 어느 필드가 원인인지 자동으로 좁혀주는 진단
    (취식기록 기준 — ⚠️ 아래 주의 참고).

    조인 키 4개 필드(ID/날짜/식사구분/메뉴명) 중 하나씩 빼고도 맞는 평가가
    있는지 센다. 사용자가 화면의 숫자만 읽어줘도 원인을 좁힐 수 있게 하려는
    목적(원문 텍스트 복붙이 안 되는 사내망 환경 고려).

    ⚠️ **취식기록 수가 맛평가 수보다 훨씬 많은 게 보통이라(응답률이 낮으므로),
    match_without_id처럼 ID를 빼고 세는 값은 과대평가되기 쉽다** — 같은 날
    같은 인기메뉴를 먹은 사람이 수백 명이면, ID 하나 빼는 것만으로 그 사람들이
    전부 "매칭 후보"로 잡히기 때문이다(실제로 그 평가를 쓴 사람인지는 무관하게).
    맛평가 수를 분모로 쓰는 `diagnose_match_failure_by_evaluation()`이 훨씬
    신뢰할 수 있는 신호이므로 그쪽을 우선 보는 게 좋다.
    """
    without_id: set[tuple] = set()
    without_date: set[tuple] = set()
    without_meal_type: set[tuple] = set()
    without_menu: set[tuple] = set()
    for ev in evaluations:
        knox_id = ev.knox_id.strip()
        menu = _normalize_menu(ev.menu_name)
        without_id.add((ev.eaten_date, ev.meal_type, menu))
        without_date.add((knox_id, ev.meal_type, menu))
        without_meal_type.add((knox_id, ev.eaten_date, menu))
        without_menu.add((knox_id, ev.eaten_date, ev.meal_type))

    result = {
        "total_transactions": len(transactions),
        "total_evaluations": len(evaluations),
        "full_match": 0,
        "match_without_id": 0,
        "match_without_date": 0,
        "match_without_meal_type": 0,
        "match_without_menu": 0,
    }
    eval_index = {
        _eval_key(ev.knox_id, ev.eaten_date, ev.meal_type, ev.menu_name): ev for ev in evaluations
    }
    for tx in transactions:
        knox_id = employee_key(tx.employee_id, employee_mapping)
        date = tx.eaten_at.date()
        menu = _normalize_menu(tx.menu_display_name)

        if _eval_key(knox_id, date, tx.meal_type, tx.menu_display_name) in eval_index:
            result["full_match"] += 1
        if (date, tx.meal_type, menu) in without_id:
            result["match_without_id"] += 1
        if (knox_id, tx.meal_type, menu) in without_date:
            result["match_without_date"] += 1
        if (knox_id, date, menu) in without_meal_type:
            result["match_without_meal_type"] += 1
        if (knox_id, date, tx.meal_type) in without_menu:
            result["match_without_menu"] += 1
    return result


def diagnose_match_failure_by_evaluation(
    transactions: list[ParsedMealTransactionRow],
    evaluations: list[ParsedTasteEvalRow],
    *,
    employee_mapping: dict[str, str] | None = None,
) -> dict[str, int]:
    """`diagnose_match_failure()`와 같은 목적이지만 **맛평가 건수를 분모로** 센다.

    맛평가는 응답률이 낮아 취식기록보다 훨씬 적은 게 정상이라(예: 취식기록
    45만 건에 맛평가 1,700건), 이쪽이 훨씬 정확한 신호다 — 모든 카운트가
    `len(evaluations)`를 못 넘는다(취식기록 기준 진단은 인기메뉴 때문에 부풀려질
    수 있음).
    """
    tx_full_keys: set[tuple] = set()
    without_id: set[tuple] = set()
    without_date: set[tuple] = set()
    without_meal_type: set[tuple] = set()
    without_menu: set[tuple] = set()
    for tx in transactions:
        knox_id = employee_key(tx.employee_id, employee_mapping)
        date = tx.eaten_at.date()
        menu = _normalize_menu(tx.menu_display_name)
        tx_full_keys.add((knox_id, date, tx.meal_type, menu))
        without_id.add((date, tx.meal_type, menu))
        without_date.add((knox_id, tx.meal_type, menu))
        without_meal_type.add((knox_id, date, menu))
        without_menu.add((knox_id, date, tx.meal_type))

    result = {
        "total_evaluations": len(evaluations),
        "full_match": 0,
        "match_without_id": 0,
        "match_without_date": 0,
        "match_without_meal_type": 0,
        "match_without_menu": 0,
    }
    for ev in evaluations:
        knox_id = ev.knox_id.strip()
        menu = _normalize_menu(ev.menu_name)

        if (knox_id, ev.eaten_date, ev.meal_type, menu) in tx_full_keys:
            result["full_match"] += 1
        if (ev.eaten_date, ev.meal_type, menu) in without_id:
            result["match_without_id"] += 1
        if (knox_id, ev.meal_type, menu) in without_date:
            result["match_without_date"] += 1
        if (knox_id, ev.eaten_date, menu) in without_meal_type:
            result["match_without_meal_type"] += 1
        if (knox_id, ev.eaten_date, ev.meal_type) in without_menu:
            result["match_without_menu"] += 1
    return result


def merge_transactions_with_taste(
    transactions: list[ParsedMealTransactionRow],
    evaluations: list[ParsedTasteEvalRow],
    *,
    only_normal_status: bool = True,
    employee_mapping: dict[str, str] | None = None,
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
            employee_key(tx.employee_id, employee_mapping),
            tx.eaten_at.date(),
            tx.meal_type,
            tx.menu_display_name,
        )
        evaluation = eval_index.get(key)

        merged.append(
            ParsedMealLogRow(
                eaten_at=tx.eaten_at,
                employee_id=tx.employee_id,
                meal_type=tx.meal_type,
                corner_name=tx.corner_name,
                menu_name=_normalize_menu(tx.menu_display_name) or tx.menu_code_name or None,
                company_name=tx.company_name,
                taste_score=evaluation.taste_score if evaluation else None,
                comment=evaluation.comment if evaluation else None,
            )
        )
    return merged
