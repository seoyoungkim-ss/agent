"""add new_menu_override/new_menu_marked_on to menu_master

Revision ID: c1a2f6e9b3d4
Revises: 8f3c9a1e5d21
Create Date: 2026-07-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a2f6e9b3d4'
down_revision: Union[str, None] = '8f3c9a1e5d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('menu_master', sa.Column('new_menu_override', sa.Boolean(), nullable=True))
    op.add_column('menu_master', sa.Column('new_menu_marked_on', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('menu_master', 'new_menu_marked_on')
    op.drop_column('menu_master', 'new_menu_override')
