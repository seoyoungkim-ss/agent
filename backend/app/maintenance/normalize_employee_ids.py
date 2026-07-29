"""이미 적재된 데이터 중 사번이 "12345678.0"처럼 남아있는 경우를 정리한다.

`app/services/master_data.py`의 `normalize_employee_id()`는 **앞으로 들어오는**
데이터에만 적용된다. 정규화가 배포되기 전에 이미 적재된 과거 데이터는
employee_master에 "12345678"과 "12345678.0"이 서로 다른 사번(행)으로 남아있을
수 있으므로, 이 스크립트로 한 번 병합해야 한다.

사용법 (backend/ 디렉토리에서):
    python -m app.maintenance.normalize_employee_ids

여러 번 실행해도 안전하다(idempotent) — 이미 정리됐으면 조용히 종료한다. 실행
후에는 daily_division_stats/employee_taste_profile을 다시 계산해야 한다(안내
메시지 참고).
"""

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.logs import MealLog
from app.models.master import EmployeeMaster
from app.models.stats import EmployeeTasteProfile
from app.services.master_data import get_or_create_employee, normalize_employee_id


def normalize_employee_ids(db: Session) -> int:
    """returns: 재배정된 meal_log 행 수."""
    bad_employees = [
        e for e in db.query(EmployeeMaster).all() if normalize_employee_id(e.employee_id) != e.employee_id
    ]
    if not bad_employees:
        return 0

    reassigned = 0
    for bad in bad_employees:
        canonical_id = normalize_employee_id(bad.employee_id)
        canonical = get_or_create_employee(db, canonical_id, bad.company_name)
        reassigned += (
            db.query(MealLog)
            .filter(MealLog.employee_id == bad.employee_id)
            .update({MealLog.employee_id: canonical.employee_id})
        )
        db.query(EmployeeTasteProfile).filter(EmployeeTasteProfile.employee_id == bad.employee_id).delete()
        db.delete(bad)
    db.commit()
    return reassigned


def run() -> None:
    db = SessionLocal()
    try:
        reassigned = normalize_employee_ids(db)
        if reassigned == 0:
            print("정리할 사번(.0 표기)이 없습니다 (이미 정리됐거나 해당 없음).")
            return
        print(f"✅ 사번의 '.0' 표기를 정리했습니다 (meal_log {reassigned}행 재배정).")
        print("⚠️ daily_division_stats/daily_corner_stats, employee_taste_profile을 다시 계산해야 합니다 —")
        print("   '최근 180일 배치 집계 재계산' 버튼과 POST /api/analysis/users/taste-profile/recompute를 호출하세요.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
