"""widen weekly_menu_plan.menu_role for 건강가든

MenuRole은 native_enum=False라 VARCHAR로 저장되고, 길이는 가장 긴 멤버값에서
나온다. 기존 멤버가 "메인"/"부찬"(2자)뿐이라 컬럼이 VARCHAR(2)로 만들어져 있어
"건강가든"(4자)을 넣으면 값이 잘리거나 에러가 난다. 여유를 두고 8자로 넓힌다.

Revision ID: e7b4c2915f30
Revises: d6ad762b4b92
Create Date: 2026-08-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b4c2915f30'
down_revision: Union[str, None] = 'd6ad762b4b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'weekly_menu_plan',
        'menu_role',
        existing_type=sa.String(length=2),
        type_=sa.String(length=8),
        existing_nullable=False,
    )


def downgrade() -> None:
    # 건강가든 행이 남아 있으면 축소가 실패한다 — 되돌릴 땐 먼저 지워야 한다.
    op.execute("DELETE FROM weekly_menu_plan WHERE menu_role = '건강가든'")
    op.alter_column(
        'weekly_menu_plan',
        'menu_role',
        existing_type=sa.String(length=8),
        type_=sa.String(length=2),
        existing_nullable=False,
    )
