"""weekly_menu_plan 한 슬롯에 같은 메뉴가 두 번 들어가지 못하게 막는다

2026-08 실사용 신고("부찬이 두번씩 들어갔고")의 재발 방지. 재적재가 관리자
수동 수정 행을 남긴 채 payload를 통째로 다시 넣어 중복이 생겼는데, **에러 없이
조용히** 데이터가 망가졌다. 코드는 고쳤지만 같은 종류의 사고가 다시 나면
이번엔 즉시 터지게 한다.

⚠️ **이 마이그레이션은 기존 중복을 먼저 정리한다.** 안 그러면 인덱스 생성이
실패한다 — 그리고 그건 운영 DB에서 실패한다는 뜻이다.
남기는 행의 우선순위는 `app/maintenance/dedupe_weekly_menu_plan.py`와 같다:
관리자수동 > LLM추정 > 규칙기반, 동률이면 가장 먼저 들어온 행(작은 id).
사람이 손으로 고친 판단을 우선 보존한다.

⚠️ autogenerate로 만들지 않았다. 이 레포에서 autogenerate를 돌리면 §50의 성능용
복합 인덱스를 전부 DROP하려 든다(모델에 선언이 없어서). §53.7 참고.

Revision ID: d2a91f5c7e40
Revises: c8f387ed003d
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2a91f5c7e40'
down_revision: Union[str, None] = 'c8f387ed003d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = 'uq_weekly_menu_plan_slot_menu_role'


def upgrade() -> None:
    # 1) 기존 중복 정리. role_source 값은 native_enum=False라 VARCHAR로 들어있다.
    op.execute(
        sa.text(
            """
            DELETE FROM weekly_menu_plan
            WHERE id IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY plan_date, corner_id, meal_type, menu_id, menu_role
                        ORDER BY
                            CASE role_source
                                WHEN '관리자수동' THEN 0
                                WHEN 'LLM추정'   THEN 1
                                ELSE 2
                            END,
                            id
                    ) AS rn
                    FROM weekly_menu_plan
                ) ranked
                WHERE rn > 1
            )
            """
        )
    )

    # 2) 이제 유일성이 보장되므로 인덱스를 건다.
    op.create_index(
        INDEX_NAME,
        'weekly_menu_plan',
        ['plan_date', 'corner_id', 'meal_type', 'menu_id', 'menu_role'],
        unique=True,
    )


def downgrade() -> None:
    # 지워진 중복 행은 되돌리지 않는다 — 애초에 데이터 오염이었다.
    op.drop_index(INDEX_NAME, table_name='weekly_menu_plan')
