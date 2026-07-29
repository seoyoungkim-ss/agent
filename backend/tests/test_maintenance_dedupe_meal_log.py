import datetime as dt

from app.maintenance.dedupe_meal_log import dedupe_meal_log
from app.models.enums import Division, MealType, TasteScore
from app.models.logs import MealLog
from app.models.master import CornerMaster, EmployeeMaster


def _make_log(employee_id, corner_id, taste_score=None, loaded_at=None) -> MealLog:
    return MealLog(
        eaten_at=dt.datetime(2026, 6, 25, 12, 0, 0),
        employee_id=employee_id,
        meal_type=MealType.LUNCH,
        corner_id=corner_id,
        taste_score=taste_score,
        loaded_at=loaded_at or dt.datetime(2026, 6, 25, 12, 5, 0),
    )


def test_dedupe_removes_exact_duplicate_rows_keeping_taste_score(db_session):
    corner = CornerMaster(corner_name="한식")
    employee = EmployeeMaster(employee_id="E1", division=Division.OTHER)
    db_session.add_all([corner, employee])
    db_session.flush()

    unmatched = _make_log("E1", corner.corner_id, taste_score=None, loaded_at=dt.datetime(2026, 6, 25, 12, 0, 0))
    matched = _make_log(
        "E1", corner.corner_id, taste_score=TasteScore.DELICIOUS, loaded_at=dt.datetime(2026, 6, 25, 13, 0, 0)
    )
    db_session.add_all([unmatched, matched])
    db_session.commit()

    removed = dedupe_meal_log(db_session)
    assert removed == 1

    remaining = db_session.query(MealLog).filter_by(employee_id="E1").all()
    assert len(remaining) == 1
    assert remaining[0].taste_score == TasteScore.DELICIOUS


def test_dedupe_keeps_rows_that_differ_in_corner(db_session):
    corner_a = CornerMaster(corner_name="한식")
    corner_b = CornerMaster(corner_name="일품")
    employee = EmployeeMaster(employee_id="E1", division=Division.OTHER)
    db_session.add_all([corner_a, corner_b, employee])
    db_session.flush()

    db_session.add_all(
        [_make_log("E1", corner_a.corner_id), _make_log("E1", corner_b.corner_id)]
    )
    db_session.commit()

    removed = dedupe_meal_log(db_session)
    assert removed == 0
    assert db_session.query(MealLog).filter_by(employee_id="E1").count() == 2


def test_dedupe_is_idempotent(db_session):
    corner = CornerMaster(corner_name="한식")
    employee = EmployeeMaster(employee_id="E1", division=Division.OTHER)
    db_session.add_all([corner, employee])
    db_session.flush()
    db_session.add(_make_log("E1", corner.corner_id))
    db_session.commit()

    assert dedupe_meal_log(db_session) == 0
    assert dedupe_meal_log(db_session) == 0
