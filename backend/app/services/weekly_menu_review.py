"""주간 식단표 검토/관리 화면 — 식당에서 2주 전에 전달하는 식단표를 관리자가
확인하고(주찬/부찬 분류가 틀렸으면 수정), 1주 전 마감까지 개선의견을 남길 수
있게 한다(사용자 확인, 2026-07).
"""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.enums import MenuRole, MenuRoleSource
from app.models.logs import WeeklyMenuFeedback, WeeklyMenuPlan
from app.models.master import CornerMaster, MenuMaster

FEEDBACK_LEAD_DAYS = 7  # plan_date - 7일까지 개선의견 제출 가능


def feedback_deadline(plan_date: dt.date) -> dt.date:
    """순수 함수 — 그 날짜 메뉴에 대한 개선의견 제출 마감일."""
    return plan_date - dt.timedelta(days=FEEDBACK_LEAD_DAYS)


@dataclass(frozen=True)
class WeeklyMenuPlanItem:
    plan_id: int
    menu_id: int
    menu_name: str
    role_source: str


@dataclass(frozen=True)
class WeeklyMenuSlot:
    plan_date: dt.date
    corner_id: int
    corner_name: str
    meal_type: str
    main: WeeklyMenuPlanItem | None
    sides: list[WeeklyMenuPlanItem]
    # 건강가든은 식단표 엑셀에 없어 담당자가 화면에서 직접 입력한다(2026-08).
    # 부찬과 섞으면 "부찬 조합" 비교가 오염되므로 처음부터 따로 담는다.
    health_garden: list[WeeklyMenuPlanItem]
    feedback_deadline: dt.date
    is_past_deadline: bool


def group_weekly_menu_rows(rows: list[tuple], *, today: dt.date) -> list[WeeklyMenuSlot]:
    """순수 함수 — (plan_id, plan_date, corner_id, corner_name, meal_type, menu_id,
    menu_name, menu_role, role_source) 튜플들을 (plan_date, corner_id, meal_type)
    단위로 묶는다."""
    slots: dict[tuple[dt.date, int, str], dict] = {}
    for plan_id, plan_date, corner_id, corner_name, meal_type, menu_id, menu_name, menu_role, role_source in rows:
        key = (plan_date, corner_id, meal_type)
        slot = slots.setdefault(
            key,
            {
                "plan_date": plan_date,
                "corner_id": corner_id,
                "corner_name": corner_name,
                "meal_type": meal_type,
                "main": None,
                "sides": [],
                "health_garden": [],
            },
        )
        item = WeeklyMenuPlanItem(
            plan_id=plan_id, menu_id=menu_id, menu_name=menu_name, role_source=role_source
        )
        if menu_role == MenuRole.HEALTH_GARDEN:
            slot["health_garden"].append(item)
        elif menu_role == MenuRole.MAIN and slot["main"] is None:
            slot["main"] = item
        else:
            # menu_role이 MAIN인데 그 슬롯에 이미 main이 있으면(데이터 정합성
            # 문제 — 예: 관리자가 부찬을 메인으로 고치면서 기존 메인을 아직
            # 안 내렸을 때) 조용히 버리지 않고 sides에 넣어 화면에서 보이게 한다.
            slot["sides"].append(item)

    results = []
    for (plan_date, _corner_id, _meal_type), slot in slots.items():
        deadline = feedback_deadline(plan_date)
        results.append(
            WeeklyMenuSlot(
                plan_date=slot["plan_date"],
                corner_id=slot["corner_id"],
                corner_name=slot["corner_name"],
                meal_type=slot["meal_type"],
                main=slot["main"],
                sides=slot["sides"],
                # 담당자가 입력한 순서를 그대로 보여준다 — 입력 텍스트 상자와
                # 화면 표시 순서가 어긋나면 수정할 때 헷갈린다. plan_id는
                # set_health_garden_menus가 입력 순서대로 넣으므로 그 대용이다.
                health_garden=sorted(slot["health_garden"], key=lambda i: i.plan_id),
                feedback_deadline=deadline,
                is_past_deadline=today > deadline,
            )
        )
    results.sort(key=lambda s: (s.plan_date, s.corner_name))
    return results


def build_weekly_menu_slots(
    db: Session, period_start: dt.date, period_end: dt.date, *, today: dt.date | None = None
) -> list[WeeklyMenuSlot]:
    rows = (
        db.query(
            WeeklyMenuPlan.id,
            WeeklyMenuPlan.plan_date,
            WeeklyMenuPlan.corner_id,
            CornerMaster.corner_name,
            WeeklyMenuPlan.meal_type,
            WeeklyMenuPlan.menu_id,
            MenuMaster.menu_name,
            WeeklyMenuPlan.menu_role,
            WeeklyMenuPlan.role_source,
        )
        .join(CornerMaster, WeeklyMenuPlan.corner_id == CornerMaster.corner_id)
        .join(MenuMaster, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .filter(WeeklyMenuPlan.plan_date.between(period_start, period_end))
        .all()
    )
    return group_weekly_menu_rows(rows, today=today or dt.date.today())


def set_menu_role(db: Session, plan_id: int, menu_role: MenuRole) -> WeeklyMenuPlan | None:
    """관리자가 역할을 수동으로 고친다 — role_source를 MANUAL로 잠가 이후 LLM
    일괄 재분류(weekly_menu_role_llm.py)가 이 행을 건드리지 않게 한다.

    MAIN으로 바꾸는 경우, 같은 슬롯(plan_date, corner_id, meal_type)에 이미
    MAIN인 다른 행이 있으면 자동으로 SIDE로 내린다 — 안 그러면 한 슬롯에
    MAIN이 2개 남아 group_weekly_menu_rows가 어느 쪽을 "메인"으로 보여줄지와
    _planned_main_menu_id(simulation.py)가 실제로 고르는 행이 서로 달라질 수
    있다(실사용 확인, 2026-07). 내려간 행도 이 조작의 직접적인 결과이므로
    함께 MANUAL로 표시한다.
    """
    plan = db.get(WeeklyMenuPlan, plan_id)
    if plan is None:
        return None

    if menu_role == MenuRole.MAIN:
        other_mains = (
            db.query(WeeklyMenuPlan)
            .filter(
                WeeklyMenuPlan.plan_date == plan.plan_date,
                WeeklyMenuPlan.corner_id == plan.corner_id,
                WeeklyMenuPlan.meal_type == plan.meal_type,
                WeeklyMenuPlan.menu_role == MenuRole.MAIN,
                WeeklyMenuPlan.id != plan_id,
            )
            .all()
        )
        for other in other_mains:
            other.menu_role = MenuRole.SIDE
            other.role_source = MenuRoleSource.MANUAL

    plan.menu_role = menu_role
    plan.role_source = MenuRoleSource.MANUAL
    db.commit()
    db.refresh(plan)
    return plan


def add_feedback(db: Session, plan_date: dt.date, corner_id: int, comment: str) -> WeeklyMenuFeedback:
    feedback = WeeklyMenuFeedback(plan_date=plan_date, corner_id=corner_id, comment=comment)
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def list_feedback(db: Session, period_start: dt.date, period_end: dt.date) -> list[WeeklyMenuFeedback]:
    return (
        db.query(WeeklyMenuFeedback)
        .filter(WeeklyMenuFeedback.plan_date.between(period_start, period_end))
        .order_by(WeeklyMenuFeedback.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# 건강가든 수기 입력 (2026-08, 2순위)
# ---------------------------------------------------------------------------
# 건강가든은 식단표 엑셀에 아직 안 들어온다. 담당자가 "대략 5개 종류가 반복"
# 이라고 해서, 정식 데이터 유입 전까지 화면에서 메뉴명을 텍스트로 입력받아
# weekly_menu_plan에 MenuRole.HEALTH_GARDEN으로 적재한다. 별도 테이블을 안 만든
# 이유는, 같은 테이블에 있어야 회전 이력·중복 판정이 메인/부찬과 한꺼번에
# 돌아가기 때문이다(요청사항이 "메인/부찬/건강가든 조합 중복 최소화"였다).


def parse_menu_names(raw: str) -> list[str]:
    """순수 함수 — 쉼표/줄바꿈으로 구분된 입력을 메뉴명 목록으로.

    담당자가 엑셀에서 복사해 붙여넣는 경우를 감안해 탭도 구분자로 본다.
    중복은 입력 순서를 유지한 채 제거한다.
    """
    tokens = raw.replace("\t", ",").replace("\n", ",").split(",")
    seen: list[str] = []
    for token in tokens:
        name = token.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def set_health_garden_menus(
    db: Session, plan_date: dt.date, corner_id: int, meal_type: str, menu_names: list[str]
) -> list[WeeklyMenuPlan]:
    """그 슬롯의 건강가든 목록을 통째로 교체한다(덮어쓰기).

    부분 수정(추가/삭제)이 아니라 전체 교체인 이유: 화면이 텍스트 상자 하나라
    "지금 이 슬롯의 건강가든은 이거다"를 통째로 보내는 게 입력 UI와 일치하고,
    빈 문자열을 보내면 전부 지우는 동작이 자연스럽게 나온다.

    메뉴 마스터에 없는 이름은 새로 만든다 — 건강가든 메뉴는 취식기록에 안
    잡혀서 마스터에 없을 수 있는데, 여기서 막으면 입력 자체가 불가능해진다.
    """
    db.query(WeeklyMenuPlan).filter(
        WeeklyMenuPlan.plan_date == plan_date,
        WeeklyMenuPlan.corner_id == corner_id,
        WeeklyMenuPlan.meal_type == meal_type,
        WeeklyMenuPlan.menu_role == MenuRole.HEALTH_GARDEN,
    ).delete(synchronize_session=False)

    created = []
    for name in menu_names:
        menu = db.query(MenuMaster).filter_by(menu_name=name).one_or_none()
        if menu is None:
            menu = MenuMaster(menu_name=name)
            db.add(menu)
            db.flush()
        row = WeeklyMenuPlan(
            plan_date=plan_date,
            corner_id=corner_id,
            meal_type=meal_type,
            menu_id=menu.menu_id,
            menu_role=MenuRole.HEALTH_GARDEN,
            is_new_menu=False,
            source_row_raw=None,
            role_source=MenuRoleSource.MANUAL,
        )
        db.add(row)
        created.append(row)

    db.commit()
    for row in created:
        db.refresh(row)
    return created
