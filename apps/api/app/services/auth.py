"""鉴权 service · 密码哈希 + DB Session + 验证 token gen/check。

设计(0006 ADR 2026-05-21 回归后):
- 密码:argon2id(passlib 内置,无新依赖)
- **登录态:DB Session 表(替代 JWT)**
  · 7 天滚动 TTL · 每次 verify 续 7 天
  · 单用户上限 5 设备(超出 evict 最旧)
  · token = secrets.token_urlsafe(32) · DB 存 sha256(token) 16 进制
  · 现有 JWT 用户:JWT 已不在 session 表 · deps.py 自然 401 · 用户重登
- 验证 token(邮箱验证):`secrets.token_urlsafe(48)` 一次性,24h 有效
- 保留 issue_access_token / decode_access_token 仅为 type compat · 实际未使用
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.session import Session as AuthSession
from app.models.user import User
from app.models.verification_token import TokenPurpose, VerificationToken

logger = logging.getLogger(__name__)

JWT_ALG = "HS256"
ACCESS_TOKEN_TTL = timedelta(days=7)
VERIFICATION_TOKEN_TTL = timedelta(hours=24)
SESSION_TTL = timedelta(days=7)       # 7 天滚动
MAX_SESSIONS_PER_USER = 5             # 单用户最多 5 设备

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# =====================
# 密码哈希
# =====================

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)  # type: ignore[no-any-return]


def verify_password(plain: str, hashed: str | None) -> bool:
    # OAuth-only 用户 hashed=None · 不能用密码登录
    if hashed is None:
        return False
    return _pwd_context.verify(plain, hashed)  # type: ignore[no-any-return]


# =====================
# Access JWT
# =====================

def issue_access_token(user_id: UUID) -> str:
    now = datetime.now(tz=UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALG)  # type: ignore[no-any-return]


def decode_access_token(token: str) -> UUID:
    """返回 user_id;失败抛 JWTError(让调用方包成 HTTPException)。"""
    payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALG])
    sub = payload.get("sub")
    if not isinstance(sub, str):
        msg = "JWT missing sub"
        raise JWTError(msg)
    try:
        return UUID(sub)
    except ValueError as e:
        msg = f"JWT sub not a UUID: {sub}"
        raise JWTError(msg) from e


# =====================
# 验证 token(数据库支撑)
# =====================

async def create_verification_token(
    db: AsyncSession,
    *,
    user_id: UUID,
    purpose: TokenPurpose = TokenPurpose.EMAIL_VERIFICATION,
) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(tz=UTC) + VERIFICATION_TOKEN_TTL
    row = VerificationToken(
        token=token,
        user_id=user_id,
        purpose=purpose,
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush()
    logger.info("verification token created for user_id=%s purpose=%s", user_id, purpose)
    return token


async def consume_verification_token(
    db: AsyncSession,
    *,
    token: str,
    purpose: TokenPurpose = TokenPurpose.EMAIL_VERIFICATION,
) -> UUID | None:
    """成功返回 user_id,失败返回 None(已过期 / 已消费 / 不存在 / 用途错)。"""
    stmt = select(VerificationToken).where(VerificationToken.token == token)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    if row.purpose != purpose:
        return None
    if row.consumed_at is not None:
        return None
    now = datetime.now(tz=UTC)
    if row.expires_at < now:
        return None
    row.consumed_at = now
    await db.flush()
    return row.user_id


async def find_user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email.lower())
    return (await db.execute(stmt)).scalar_one_or_none()


async def find_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    stmt = select(User).where(User.id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def find_user_by_google_sub(db: AsyncSession, google_sub: str) -> User | None:
    stmt = select(User).where(User.google_sub == google_sub)
    return (await db.execute(stmt)).scalar_one_or_none()


async def find_or_create_oauth_user(
    db: AsyncSession,
    *,
    google_sub: str,
    email: str,
) -> User:
    """Google OAuth 登录入口 · 0006 ADR M1 第三波。

    匹配优先级:
      1. google_sub 命中 → 直接返回(老用户多次登录)
      2. email 命中 + 无 google_sub → 把 google_sub 写到现有 user(account linking)
      3. 都没命中 → 新建 user · 密码空 · email_verified_at = now(Google 已验邮箱)
    """
    # 1. google_sub 命中
    user = await find_user_by_google_sub(db, google_sub)
    if user is not None:
        return user

    email_norm = email.lower()

    # 2. email 命中 + 无 google_sub · account linking
    existing = await find_user_by_email(db, email_norm)
    if existing is not None:
        if existing.google_sub is None:
            existing.google_sub = google_sub
            # 顺手把 email_verified 写上(Google 已验)
            if existing.email_verified_at is None:
                existing.email_verified_at = datetime.now(tz=UTC)
            await db.flush()
        return existing

    # 3. 新建用户
    now = datetime.now(tz=UTC)
    user = User(
        email=email_norm,
        password_hash=None,           # OAuth-only · 无密码
        google_sub=google_sub,
        email_verified_at=now,        # Google 已验邮箱
        age_confirmed=True,           # OAuth 流程默认确认(后续可在 settings 让用户撤回)
    )
    db.add(user)
    await db.flush()
    logger.info("[oauth.google] created user_id=%s email=%s", user.id, email_norm)
    return user


# =====================
# Session(DB-backed · 0006 ADR 回归)
# =====================


def _hash_session_token(token: str) -> str:
    """sha256(token) hex · 64 字符。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_session(
    db: AsyncSession,
    *,
    user_id: UUID,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> str:
    """登录 / 创建新 session · 返回明文 token(只此一次)。

    若用户已有 MAX_SESSIONS_PER_USER 个活 session,evict 最旧的(按 last_used_at)。
    """
    token = secrets.token_urlsafe(32)        # 43 字符 base64url
    token_hash = _hash_session_token(token)
    now = datetime.now(tz=UTC)

    # evict 最旧的(若超上限)
    existing_stmt = (
        select(AuthSession.id)
        .where(AuthSession.user_id == user_id)
        .order_by(AuthSession.last_used_at.desc())
    )
    existing_ids = (await db.execute(existing_stmt)).scalars().all()
    if len(existing_ids) >= MAX_SESSIONS_PER_USER:
        # 删除超过上限的尾部(保留最近 MAX-1 个,腾出 1 个新位置)
        to_evict = existing_ids[MAX_SESSIONS_PER_USER - 1:]
        await db.execute(
            delete(AuthSession).where(AuthSession.id.in_(to_evict)),
        )

    row = AuthSession(
        token_hash=token_hash,
        user_id=user_id,
        user_agent=(user_agent or "")[:512] or None,
        ip_address=(ip_address or "")[:64] or None,
        created_at=now,
        last_used_at=now,
        expires_at=now + SESSION_TTL,
    )
    db.add(row)
    await db.flush()
    logger.info(
        "[session] issued user_id=%s ua=%s ip=%s",
        user_id, (user_agent or "")[:40], ip_address,
    )
    return token


async def verify_session(
    db: AsyncSession, *, token: str,
) -> User | None:
    """查 session · 校验未过期 · 续 TTL · 返回 User · 失败返回 None。

    成功的副作用:
    - last_used_at = now
    - expires_at   = now + SESSION_TTL(7 天滚动)
    """
    token_hash = _hash_session_token(token)
    now = datetime.now(tz=UTC)

    stmt = select(AuthSession).where(AuthSession.token_hash == token_hash)
    sess = (await db.execute(stmt)).scalar_one_or_none()
    if sess is None:
        return None
    if sess.expires_at < now:
        # 过期 · 顺手删
        await db.execute(
            delete(AuthSession).where(AuthSession.id == sess.id),
        )
        await db.commit()
        return None

    # 续 7 天 · 写 last_used_at · 落盘(read-only 路由也要持久化滑动 TTL)
    sess.last_used_at = now
    sess.expires_at = now + SESSION_TTL
    await db.commit()

    return await find_user_by_id(db, sess.user_id)


async def revoke_session(db: AsyncSession, *, token: str) -> bool:
    """logout · 显式失效。"""
    token_hash = _hash_session_token(token)
    result = await db.execute(
        delete(AuthSession).where(AuthSession.token_hash == token_hash),
    )
    return result.rowcount > 0


async def revoke_all_user_sessions(db: AsyncSession, *, user_id: UUID) -> int:
    """注销所有设备 · 用户改密 / 强制下线场景用。"""
    result = await db.execute(
        delete(AuthSession).where(AuthSession.user_id == user_id),
    )
    return result.rowcount or 0


async def cleanup_expired_sessions(db: AsyncSession) -> int:
    """批量清过期 · Celery beat 每日跑(M2+ 接)。"""
    now = datetime.now(tz=UTC)
    result = await db.execute(
        delete(AuthSession).where(AuthSession.expires_at < now),
    )
    return result.rowcount or 0
