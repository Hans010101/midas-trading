"""reset language_pref 'en' → 'zh'(生产 bug 修复 · docs/decisions/0047)

Revision ID: r9s0t1u2v3w4
Revises: q8r9s0t1u2v3
Create Date: 2026-07-05

★背景:i18n 刀2 短暂上线语言切换 UI 时,少数账号(Hans)的 user.language_pref 被写成 'en';
  之后 UI 撤下但脏数据留存。resolve_lang 已收窄【不再读 language_pref】(见 services/i18n/lang.py),
  但清脏数据兜底:① /auth/me 不再返 'en'(前端若展示不误导)· ② 未来海外版恢复四级时不会用旧脏值复发 bug。
★只 UPDATE language_pref='en' 的行 —— 不碰合法 'zh' / NULL · 幂等(再跑命中 0 行)· 纯数据修复不改 schema。
"""

from __future__ import annotations

from alembic import op

revision = "r9s0t1u2v3w4"
down_revision = "q8r9s0t1u2v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 表名 "user"(单数 · PG 保留字 → 双引号)· 对齐 models/user.py __tablename__="user"。
    op.execute("""UPDATE "user" SET language_pref = 'zh' WHERE language_pref = 'en'""")


def downgrade() -> None:
    # 不可逆:无法区分哪些 'zh' 原本是 'en'(数据修复迁移惯例 · downgrade no-op)。
    pass
