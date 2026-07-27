"""휴일 마스터 데이터 최초 시딩 스크립트.

사용법 (backend/ 디렉토리에서):
    python -m app.seed.run_seed_holidays

이미 존재하는 날짜는 건너뛰므로 여러 번 실행해도 안전하다(idempotent).
"""

from app.db import SessionLocal
from app.models.master import HolidayCalendar
from app.seed.holidays_2025_2026 import HOLIDAY_SEED
from app.services.holidays import is_weekend


def run() -> None:
    db = SessionLocal()
    try:
        existing = {row.calendar_date for row in db.query(HolidayCalendar).all()}
        inserted = 0
        for calendar_date, holiday_type, name, note in HOLIDAY_SEED:
            if calendar_date in existing:
                continue
            db.add(
                HolidayCalendar(
                    calendar_date=calendar_date,
                    holiday_type=holiday_type,
                    holiday_name=name,
                    is_weekend=is_weekend(calendar_date),
                    note=note,
                )
            )
            inserted += 1
        db.commit()
        print(f"휴일 {inserted}건 추가 (기존 {len(existing)}건 유지)")
    finally:
        db.close()


if __name__ == "__main__":
    run()
