"""add daily_weather table

Revision ID: a4e6d1c9b7f3
Revises: f19c3b6a4d21
Create Date: 2026-08-10 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4e6d1c9b7f3'
down_revision: Union[str, None] = 'f19c3b6a4d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'daily_weather',
        sa.Column('stat_date', sa.Date(), nullable=False),
        sa.Column('precip_mm', sa.Float(), nullable=True),
        sa.Column('had_rain', sa.Boolean(), nullable=False),
        sa.Column('avg_temp_c', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('stat_date'),
    )


def downgrade() -> None:
    op.drop_table('daily_weather')
