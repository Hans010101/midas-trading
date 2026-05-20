"""鉴权 service · 密码哈希 + JWT + 验证 token gen/check。

设计:
- 密码:argon2id(passlib 内置,无新依赖)
- JWT:python-jose HS256,sub=user_id,7d 过期(后期续期通过 refresh,M0 不做 refresh)
- 验证 token:`secrets.token_urlsafe(48)` 一次性,24h 有效;消费后 consumed_at 写时间戳
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.models.verification_token import TokenPurpose, VerificationToken

logger = logging.getLogger(__name__)

JWT_ALG = "HS256"
ACCESS_TOKEN_TTL = timedelta(days=7)
VERIFICATION_TOKEN_TTL = timedelta(hours=24)

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# =====================
# 密码哈希
# =====================

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)  # type: ignore[no-any-return]


def verify_password(plain: str, hashed: str) -> bool:
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
