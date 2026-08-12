"""add snow_cm/max_temp_c/min_temp_c to daily_weather

Revision ID: cc1556243b8c
Revises: a4e6d1c9b7f3
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc1556243b8c'
down_revision: Union[str, None] = 'a4e6d1c9b7f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('daily_weather', sa.Column('snow_cm', sa.Float(), nullable=True))
    op.add_column('daily_weather', sa.Column('max_temp_c', sa.Float(), nullable=True))
    op.add_column('daily_weather', sa.Column('min_temp_c', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('daily_weather', 'min_temp_c')
    op.drop_column('daily_weather', 'max_temp_c')
    op.drop_column('daily_weather', 'snow_cm')
