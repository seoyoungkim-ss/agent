"""menu_master.match_key — 표기가 달라 같은 메뉴가 갈라지는 걸 막는다

2026-08 신고("연어파피요트 취식현황에도 있고 주간식단표에 있는데 매칭이 안되고
있음")의 수정. 메뉴 join이 사실상 정확 문자열 비교라 `연어 파피요트`(내부 공백),
전각 괄호, 7자 원산지(`노르웨이자연산`), `(포장)` 접두사가 전부 별개 행이 됐다.

표시용 `menu_name`은 **그대로 둔다** — 담당자가 엑셀 셀과 대조해야 한다.
조회용 키만 따로 만들어 채운다.

⚠️ unique 제약은 걸지 않는다. 이미 갈라진 행들이 있어 제약을 걸면 이 마이그레이션이
운영 DB에서 실패한다. 병합은 `app/maintenance/merge_duplicate_menus.py`가 dry-run
확인을 거쳐 수행한다(취식 이력을 끊지 않도록 삭제가 아니라 remap).

⚠️ autogenerate로 만들지 않았다 — 이 레포에서 돌리면 §50의 성능 인덱스를 전부
DROP하려 든다(§53.7).

Revision ID: f19c3b6a4d21
Revises: d2a91f5c7e40
Create Date: 2026-08-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f19c3b6a4d21'
down_revision: Union[str, None] = 'd2a91f5c7e40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('menu_master', sa.Column('match_key', sa.String(length=128), nullable=True))
    op.create_index(op.f('ix_menu_master_match_key'), 'menu_master', ['match_key'], unique=False)

    # 기존 행 백필. 정규화 규칙은 파이썬(menu_name.match_key)이 단일 출처이므로
    # SQL로 흉내내지 않고 그 함수를 그대로 부른다 — 규칙이 두 벌이 되면 어긋난다.
    from app.models.master import MenuMaster
    from app.services.menu_name import match_key

    bind = op.get_bind()
    session = sa.orm.Session(bind=bind)
    try:
        for menu in session.query(MenuMaster).all():
            menu.match_key = match_key(menu.menu_name)
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    op.drop_index(op.f('ix_menu_master_match_key'), table_name='menu_master')
    op.drop_column('menu_master', 'match_key')
