"""user.avatar_id

头像选择器:user 加 avatar_id(SMALLINT nullable)· NULL/0=默认首字母,1-16=预设头像。
★ 零图片存储:只存编号,绝不存上传图。现有用户 NULL → 继续显示邮箱首字母圆底(零影响)。

Revision ID: a5b6c7d8e9fa
Revises: f4a5b6c7d8e9
Create Date: 2026-06-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a5b6c7d8e9fa'
down_revision: str | None = 'f4a5b6c7d8e9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('user', sa.Column('avatar_id', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('user', 'avatar_id')
