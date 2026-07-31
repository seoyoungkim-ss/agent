"""add satisfaction_trend/has_loyal_following to menu_performance_stats

Revision ID: d6ad762b4b92
Revises: c1a2f6e9b3d4
Create Date: 2026-07-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6ad762b4b92'
down_revision: Union[str, None] = 'c1a2f6e9b3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'menu_performance_stats',
        sa.Column(
            'satisfaction_trend',
            sa.Enum('상승', '유지', '하락', name='trenddirection', native_enum=False),
            nullable=True,
        ),
    )
    op.add_column(
        'menu_performance_stats',
        sa.Column('has_loyal_following', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('menu_performance_stats', 'has_loyal_following')
    op.drop_column('menu_performance_stats', 'satisfaction_trend')
