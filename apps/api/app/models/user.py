"""User SQLAlchemy model · 0006 鉴权策略 + M1 第三波 Google OAuth。

字段:
- id: UUID 主键
- email: unique
- password_hash: argon2id(via passlib)· **OAuth-only 用户可空**
- google_sub: Google `sub` claim · OAuth 登录唯一标识 · unique 可空
- email_verified_at: NULL 表示未验证 · OAuth 登录创建时自动写当下时间
                     (Google 已经替我们验证了邮箱)
- age_confirmed: 注册时 18+ 勾选(合规要求)
- created_at / updated_at: tz-aware UTC,server-side default
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, SmallInteger, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # OAuth-only 用户 password_hash 可空(Google 登录无密码)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Google OAuth sub claim · 同一 Google 账号 → 同一 user · 一个用户一辈子一个值
    google_sub: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    age_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 用户管理刀1:'user' | 'admin' · VARCHAR 不用 PG enum(currency/margin_mode
    # 两次 enum→varchar 先例)· 首管由迁移 a4b5c6d7e8f9 按邮箱置位(甲案)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'user'"), default="user",
    )
    # Phase 1.5 刀A:邀请码(8 位 Crockford base32)· lazy 生成于首次 GET /invite/me
    invite_code: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)
    # 用户管理刀3b-2:封禁(方案A 禁止登录)· banned_at 非空=已停用(留"何时封"可追溯)·
    # login + get_current_user 均查此字段 → 现有 session 立即失效
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 0007 watchlist:首次 GET /watchlist 触发 demo 预填后翻为 True,
    # 用户主动清空 watchlist 不会再触发(防止「删光 → 又被填回来」UX 怪圈)
    demo_prefilled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False,
    )
    # 头像选择器:NULL/0 = 默认邮箱首字母圆底;1-16 = 选了第 N 个预设头像。
    # ★ 零图片存储 —— 只存所选编号,绝不存上传图(用户只能从预设里选)。
    avatar_id: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # 铂金标记(多账户 PR-1)· ★superadmin 后台手动设 · 非付费档 · 独立于 pro 订阅。
    # is_platinum=true → resolve_plan 返 'pro'(享受 pro 权益)+ 后续 PR 解锁托管/智能交易(独立账户)。
    is_platinum: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False,
    )
    # 语言偏好(i18n Phase 0)· NULL = 跟随浏览器/cookie · 'zh'/'en'(第一批)。
    # ★双层:cookie 即时生效(复用涨跌色范式)+ 此字段登录后跨设备同步。nullable 不破存量。
    language_pref: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # 指标偏好(做T线后端 · 前端读它决定展示哪些分析)· NULL = 全默认(布林/缠论 ON · 做T OFF)·
    # ★JSONB 可扩展(未来加指标零迁移)· nullable 不破存量(现有用户 NULL → 端点合并默认)·
    #   ★纯偏好存储:不碰 boll-scan 引擎 / M1 影子 / 交易。默认与合并口径见 api/v1/user.py。
    indicator_prefs: Mapped[dict[str, bool] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
