"""add composite indexes for hot query shapes

초기 스키마 이후 meal_log / weekly_menu_plan에 인덱스가 하나도 추가된 적이 없고
전부 단일 컬럼이었다. 실사용에서 화면이 "불러오는 중"에서 멈춘다는 신고가 있어
실제 쿼리 형태를 조사한 결과, 아래 조합이 반복적으로 인덱스 없이 스캔되고 있었다
(2026-08). 각 인덱스 옆에 그 인덱스를 쓰는 호출부를 적어 둔다.

Revision ID: b3f81c47d052
Revises: e7b4c2915f30
Create Date: 2026-08-06 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b3f81c47d052'
down_revision: Union[str, None] = 'e7b4c2915f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # build_corner_daily_throughput / build_corner_daily_peak_share
    # (menu_throughput.py) — 예측 경로에서 코너마다 반복 호출된다.
    op.create_index(
        "ix_meal_log_corner_eaten", "meal_log", ["corner_id", "eaten_at"], unique=False
    )
    # build_side_combos_for_main_menu (menu_combination.py)
    op.create_index(
        "ix_meal_log_menu_eaten", "meal_log", ["menu_id", "eaten_at"], unique=False
    )
    # headcount-trend (analysis.py) — 기간 + 코너 + 끼니 동시 필터
    op.create_index(
        "ix_meal_log_eaten_corner_meal",
        "meal_log",
        ["eaten_at", "corner_id", "meal_type"],
        unique=False,
    )
    # menu-plan/performance, weekly-menu/rotation, spread-ranking
    op.create_index(
        "ix_weekly_menu_plan_date_role",
        "weekly_menu_plan",
        ["plan_date", "menu_role"],
        unique=False,
    )
    # _menu_popularity_multiplier — menu_id로 찾아 period_end 최신 1건.
    # 기존 UniqueConstraint는 (period_start, period_end, menu_id) 순서라
    # menu_id 선행 조회에 쓸 수 없다.
    op.create_index(
        "ix_menu_perf_menu_period_end",
        "menu_performance_stats",
        ["menu_id", "period_end"],
        unique=False,
    )
    # _fetch_classification_history (simulation.py) — 필터 3개 후 stat_date 정렬
    op.create_index(
        "ix_daily_corner_stats_lookup",
        "daily_corner_stats",
        ["corner_id", "meal_type", "is_holiday", "stat_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_daily_corner_stats_lookup", table_name="daily_corner_stats")
    op.drop_index("ix_menu_perf_menu_period_end", table_name="menu_performance_stats")
    op.drop_index("ix_weekly_menu_plan_date_role", table_name="weekly_menu_plan")
    op.drop_index("ix_meal_log_eaten_corner_meal", table_name="meal_log")
    op.drop_index("ix_meal_log_menu_eaten", table_name="meal_log")
    op.drop_index("ix_meal_log_corner_eaten", table_name="meal_log")
