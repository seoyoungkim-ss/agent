"""add voe_categories/voe_keywords to meal_log

Revision ID: 56b07f7edb3b
Revises: 2a034f9e204d
Create Date: 2026-07-29 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56b07f7edb3b'
down_revision: Union[str, None] = '2a034f9e204d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('meal_log', sa.Column('voe_categories', sa.ARRAY(sa.String(length=16)), nullable=True))
    op.add_column('meal_log', sa.Column('voe_keywords', sa.ARRAY(sa.String(length=64)), nullable=True))


def downgrade() -> None:
    op.drop_column('meal_log', 'voe_keywords')
    op.drop_column('meal_log', 'voe_categories')
