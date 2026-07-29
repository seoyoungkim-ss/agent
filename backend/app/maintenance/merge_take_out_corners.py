"""Take Out R/M/L로 이미 나뉘어 적재된 기존 데이터를 하나의 코너로 합친다.

`app/services/master_data.py`의 코너명 정규화는 **앞으로 들어오는** 취식기록에만
적용된다. 정규화가 배포되기 전에 이미 적재된 과거 데이터는 corner_master에
"Take Out R"/"Take Out M"/"Take Out L"이 서로 다른 corner_id로 남아있으므로,
이 스크립트로 한 번 병합해야 한다.

사용법 (backend/ 디렉토리에서):
    python -m app.maintenance.merge_take_out_corners

여러 번 실행해도 안전하다(idempotent) — 이미 병합됐으면 별칭 코너가 없어 조용히
종료한다. 실행 후에는 daily_corner_stats를 다시 계산해야 한다(안내 메시지 참고).
"""

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import CornerMaster
from app.models.stats import DailyCornerStats
from app.services.master_data import TAKE_OUT_ALIASES, TAKE_OUT_CORNER_NAME, get_or_create_corner


def merge_take_out_corners(db: Session) -> int:
    """returns: 재배정된 meal_log 행 수."""
    alias_corners = db.query(CornerMaster).filter(CornerMaster.corner_name.in_(TAKE_OUT_ALIASES)).all()
    if not alias_corners:
        return 0

    canonical, _ = get_or_create_corner(db, TAKE_OUT_CORNER_NAME)
    reassigned = 0
    for alias in alias_corners:
        if alias.corner_id == canonical.corner_id:
            continue
        reassigned += (
            db.query(MealLog)
            .filter(MealLog.corner_id == alias.corner_id)
            .update({MealLog.corner_id: canonical.corner_id})
        )
        db.query(WeeklyMenuPlan).filter(WeeklyMenuPlan.corner_id == alias.corner_id).update(
            {WeeklyMenuPlan.corner_id: canonical.corner_id}
        )
        db.query(DailyCornerStats).filter(DailyCornerStats.corner_id == alias.corner_id).delete()
        db.delete(alias)
    db.commit()
    return reassigned


def run() -> None:
    db = SessionLocal()
    try:
        reassigned = merge_take_out_corners(db)
        if reassigned == 0:
            print("병합할 Take Out 별칭 코너가 없습니다 (이미 병합됐거나 해당 없음).")
            return
        print(f"✅ Take Out R/M/L을 '{TAKE_OUT_CORNER_NAME}' 코너로 병합했습니다 (meal_log {reassigned}행 재배정).")
        print("⚠️ daily_corner_stats를 다시 계산해야 합니다 — 분석 탭의 '최근 180일 배치 집계 재계산' 버튼을")
        print("   누르거나, POST /api/analysis/daily-stats/recompute를 호출하세요.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
