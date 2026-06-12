"""user_role_admin

用户管理刀1:user 表加 role 列(VARCHAR 不用 PG enum —— currency/margin_mode
两次 enum→varchar 先例,见迁移 d5e6f7a8b9c0 / d4e5f6a7b8c9)。

同迁移置首个管理员 hans.pan007@gmail.com(调研定稿甲案:role 单一事实源=DB,
随 deploy 自动生效;rowcount=0 仅 warning 不 fail —— 测试库/新环境无此用户也能跑)。

Revision ID: a4b5c6d7e8f9
Revises: d7e8f9a0b1c2
Create Date: 2026-06-12 21:00:00.000000

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: str | None = 'd7e8f9a0b1c2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

FIRST_ADMIN_EMAIL = 'hans.pan007@gmail.com'


def upgrade() -> None:
    op.add_column(
        'user',
        sa.Column(
            'role',
            sa.String(length=16),
            server_default=sa.text("'user'"),
            nullable=False,
        ),
    )
    # 首个管理员(甲案)· 邮箱必须已注册(Hans 的 Google 账号已存在);
    # 0 行命中 = 该环境无此用户(测试库/全新环境),warning 即可,不 fail。
    result = op.get_bind().execute(
        sa.text('UPDATE "user" SET role = :role WHERE email = :email'),
        {"role": "admin", "email": FIRST_ADMIN_EMAIL},
    )
    if result.rowcount == 0:
        logger.warning(
            "首个管理员置位 0 行命中(%s 未注册)· 本环境暂无 admin",
            FIRST_ADMIN_EMAIL,
        )
    else:
        logger.info("首个管理员已置位:%s", FIRST_ADMIN_EMAIL)


def downgrade() -> None:
    op.drop_column('user', 'role')
