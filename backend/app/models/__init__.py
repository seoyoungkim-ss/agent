"""모든 모델을 임포트해 Alembic autogenerate가 메타데이터를 인식하게 한다."""

from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import CornerMaster, EmployeeMaster, HolidayCalendar, MenuMaster
from app.models.stats import (
    CongestionForecast,
    DailyCornerStats,
    DailyDivisionStats,
    EmployeeTasteProfile,
    MenuPerformanceStats,
    MonthlyVoeCluster,
)

__all__ = [
    "MealLog",
    "WeeklyMenuPlan",
    "CornerMaster",
    "EmployeeMaster",
    "HolidayCalendar",
    "MenuMaster",
    "CongestionForecast",
    "DailyCornerStats",
    "DailyDivisionStats",
    "EmployeeTasteProfile",
    "MenuPerformanceStats",
    "MonthlyVoeCluster",
]
