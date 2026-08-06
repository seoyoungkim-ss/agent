"""add llm_analysis_cache and menu ingredients

autogenerate가 함께 만든 인덱스 DROP과 menu_role 타입 변경은 **의도적으로 뺐다**:

- `ix_meal_log_*` / `ix_weekly_menu_plan_date_role` 등은 성능용으로 앞선
  마이그레이션(`b3f81c47d052`)에서 손으로 만든 것이라 모델에 선언이 없다.
  autogenerate는 "모델에 없으니 지워라"라고 보지만 지우면 §50의 성능 개선이
  통째로 되돌아간다.
- `weekly_menu_plan.menu_role`은 `e7b4c2915f30`에서 VARCHAR(8)로 넓힌 것이고
  값은 그대로다 — Enum 재선언은 실질 변화가 없다.

Revision ID: c8f387ed003d
Revises: b3f81c47d052
Create Date: 2026-08-06 04:03:26.060899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f387ed003d'
down_revision: Union[str, None] = 'b3f81c47d052'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_analysis_cache',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('subject_key', sa.String(length=64), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('facts_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_llm_analysis_cache_created_at'), 'llm_analysis_cache', ['created_at'], unique=False
    )
    op.create_index(op.f('ix_llm_analysis_cache_kind'), 'llm_analysis_cache', ['kind'], unique=False)
    op.create_index(
        op.f('ix_llm_analysis_cache_subject_key'), 'llm_analysis_cache', ['subject_key'], unique=False
    )
    # (kind, subject_key)로 최신 1건을 찾는 게 유일한 조회 형태다.
    op.create_index(
        'ix_llm_analysis_cache_lookup',
        'llm_analysis_cache',
        ['kind', 'subject_key', 'created_at'],
        unique=False,
    )

    op.add_column('menu_master', sa.Column('ingredients', sa.ARRAY(sa.String(length=32)), nullable=True))
    op.add_column(
        'menu_master',
        sa.Column(
            'ingredients_source',
            sa.Enum('규칙기반', 'LLM추정', '관리자수동', name='foodvectorsource', native_enum=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('menu_master', 'ingredients_source')
    op.drop_column('menu_master', 'ingredients')
    op.drop_index('ix_llm_analysis_cache_lookup', table_name='llm_analysis_cache')
    op.drop_index(op.f('ix_llm_analysis_cache_subject_key'), table_name='llm_analysis_cache')
    op.drop_index(op.f('ix_llm_analysis_cache_kind'), table_name='llm_analysis_cache')
    op.drop_index(op.f('ix_llm_analysis_cache_created_at'), table_name='llm_analysis_cache')
    op.drop_table('llm_analysis_cache')
