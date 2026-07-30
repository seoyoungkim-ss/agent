"""add role_source to weekly_menu_plan, add weekly_menu_feedback table

Revision ID: 8f3c9a1e5d21
Revises: 56b07f7edb3b
Create Date: 2026-07-30 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f3c9a1e5d21'
down_revision: Union[str, None] = '56b07f7edb3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'weekly_menu_plan',
        sa.Column(
            'role_source',
            sa.Enum('규칙기반', 'LLM추정', '관리자수동', name='menurolesource', native_enum=False),
            nullable=True,
        ),
    )
    # 기존 행(이 컬럼이 생기기 전에 적재된 것)은 전부 ingestion-tool의 위치
    # 규칙으로 채워진 것이므로 규칙기반으로 백필한다.
    op.execute("UPDATE weekly_menu_plan SET role_source = '규칙기반' WHERE role_source IS NULL")
    op.alter_column('weekly_menu_plan', 'role_source', nullable=False)

    op.create_table(
        'weekly_menu_feedback',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('plan_date', sa.Date(), nullable=False),
        sa.Column('corner_id', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['corner_id'], ['corner_master.corner_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_weekly_menu_feedback_plan_date'), 'weekly_menu_feedback', ['plan_date'])
    op.create_index(op.f('ix_weekly_menu_feedback_corner_id'), 'weekly_menu_feedback', ['corner_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_weekly_menu_feedback_corner_id'), table_name='weekly_menu_feedback')
    op.drop_index(op.f('ix_weekly_menu_feedback_plan_date'), table_name='weekly_menu_feedback')
    op.drop_table('weekly_menu_feedback')
    op.drop_column('weekly_menu_plan', 'role_source')
