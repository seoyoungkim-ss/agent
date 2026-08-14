"""add keywords to llm_analysis_cache

Revision ID: 9a3f7c1e2b6d
Revises: cc1556243b8c
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a3f7c1e2b6d'
down_revision: Union[str, None] = 'cc1556243b8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('llm_analysis_cache', sa.Column('keywords', sa.ARRAY(sa.String(length=64)), nullable=True))


def downgrade() -> None:
    op.drop_column('llm_analysis_cache', 'keywords')
