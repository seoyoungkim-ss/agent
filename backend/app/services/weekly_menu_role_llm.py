"""주간 식단표 주찬/부찬 LLM 일괄 재분류.

ingestion-tool의 위치 규칙(첫 항목=메인)이 셀 병합 등으로 틀리기 쉬워
(docs/PRD.md에도 "실제 데이터로 검증 필요"라고 명시, 사용자도 확인),
`food_vector_tagging.py`와 같은 "규칙 → LLM 보강" 패턴으로 백엔드에서 재분류
배치를 추가한다. `role_source`가 "관리자수동"인 행은 절대 건드리지 않는다
(food_vector의 MANUAL 잠금과 동일한 보호 방식).
"""

import datetime as dt

from sqlalchemy.orm import Session

from app.models.enums import MenuRole, MenuRoleSource
from app.models.logs import WeeklyMenuPlan
from app.models.master import MenuMaster
from app.services.llm_client import InternalLLMClient


def _parse_role_response(response: str, menu_names: list[str]) -> dict[str, MenuRole] | None:
    """'메인: OO' / '부찬: OO, OO' 형식 응답을 파싱한다. 메인이 정확히 하나가
    아니거나, 응답에 없는 이름이 있으면 None(이번 재분류는 실패로 간주, 다음
    배치에서 재시도)."""
    main_names: list[str] = []
    side_names: list[str] = []
    for line in response.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        label = label.strip()
        names = [n.strip() for n in value.split(",") if n.strip()]
        if "메인" in label:
            main_names.extend(names)
        elif "부찬" in label:
            side_names.extend(names)

    if len(main_names) != 1:
        return None

    result: dict[str, MenuRole] = {}
    for name in menu_names:
        if name == main_names[0]:
            result[name] = MenuRole.MAIN
        elif name in side_names:
            result[name] = MenuRole.SIDE
        else:
            return None  # 응답에 안 나온 이름이 있으면 신뢰 못 함
    return result


async def classify_menu_roles_via_llm(
    llm_client: InternalLLMClient, menu_names: list[str]
) -> dict[str, MenuRole] | None:
    """한 슬롯(같은 날짜·코너·식사구분에서 나온 항목들)의 메인/부찬을 LLM에게 묻는다."""
    if len(menu_names) < 2:
        return None  # 항목이 하나뿐이면 재분류할 게 없음
    names_text = ", ".join(menu_names)
    prompt = (
        f"다음은 구내식당 하루 식단의 항목들입니다: {names_text}. 이 중 메인 메뉴(주찬) 딱 "
        "하나와 나머지 부찬을 구분하세요. 다른 설명 없이 다음 형식으로만 답하세요:\n"
        "메인: OO\n부찬: OO, OO"
    )
    response = await llm_client.chat_complete([{"role": "user", "content": prompt}])
    return _parse_role_response(response, menu_names)


async def reclassify_weekly_menu_roles(
    db: Session, llm_client: InternalLLMClient, period_start: dt.date, period_end: dt.date
) -> int:
    """`role_source != 관리자수동`인 행만 대상으로, `source_row_raw`가 같은 행들
    (같은 셀에서 나온 항목들)을 묶어 LLM 재분류를 요청하고 반영한다.
    반환값은 실제로 재분류된 슬롯(그룹) 수."""
    rows = (
        db.query(WeeklyMenuPlan, MenuMaster.menu_name)
        .join(MenuMaster, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .filter(
            WeeklyMenuPlan.plan_date.between(period_start, period_end),
            WeeklyMenuPlan.role_source != MenuRoleSource.MANUAL,
            WeeklyMenuPlan.source_row_raw.isnot(None),
        )
        .all()
    )

    groups: dict[tuple, list[tuple[WeeklyMenuPlan, str]]] = {}
    for plan, menu_name in rows:
        key = (plan.plan_date, plan.corner_id, plan.meal_type, plan.source_row_raw)
        groups.setdefault(key, []).append((plan, menu_name))

    reclassified = 0
    for group in groups.values():
        if len(group) < 2:
            continue  # 항목이 하나뿐이면 재분류할 필요 없음(이미 메인으로 봐야 함)
        menu_names = [name for _, name in group]
        role_map = await classify_menu_roles_via_llm(llm_client, menu_names)
        if role_map is None:
            continue
        for plan, menu_name in group:
            plan.menu_role = role_map[menu_name]
            plan.role_source = MenuRoleSource.LLM
        reclassified += 1

    db.commit()
    return reclassified
