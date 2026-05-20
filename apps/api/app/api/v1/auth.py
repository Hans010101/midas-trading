"""鉴权路由 · /api/v1/auth/*

- POST /register · 创建账号 + 发验证邮件
- POST /login    · 邮箱+密码 → JWT(必须 email_verified)
- POST /verify   · 用 token 完成邮箱验证
- POST /resend-verification · 重发验证邮件
- GET  /me       · 当前用户(Bearer JWT)
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.models.user import User
from app.services.auth import (
    consume_verification_token,
    create_verification_token,
    find_user_by_email,
    hash_password,
    issue_access_token,
    verify_password,
)
from app.services.email import send_verification_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


# =====================
# Request / Response models
# =====================


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    age_confirmed: bool


class RegisterOut(BaseModel):
    user_id: str
    email: str
    needs_verification: bool


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class VerifyIn(BaseModel):
    token: str


class VerifyOut(BaseModel):
    verified: bool
    email: str


class ResendIn(BaseModel):
    email: EmailStr


class MeOut(BaseModel):
    user_id: str
    email: str
    email_verified: bool


# =====================
# 路由
# =====================


def _public_base_url() -> str:
    return os.getenv("PUBLIC_WEB_URL", "http://localhost:3000")


@router.post(
    "/register",
    response_model=RegisterOut,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterIn, db: DbDep) -> RegisterOut:
    if not payload.age_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须确认年满 18 周岁",
        )
    email = payload.email.lower()
    existing = await find_user_by_email(db, email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已注册",
        )
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        age_confirmed=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = await create_verification_token(db, user_id=user.id)
    verify_url = f"{_public_base_url()}/verify-email?token={token}"
    try:
        await send_verification_email(to=email, verify_url=verify_url)
    except Exception:  # noqa: BLE001
        # Resend 挂掉不应阻塞注册流程;0006 允许 24h 内 retry
        logger.exception(
            "注册成功但发邮件失败 · email=%s · 用户可用 /resend-verification 重试",
            email,
        )

    await db.commit()
    return RegisterOut(
        user_id=str(user.id),
        email=user.email,
        needs_verification=True,
    )


@router.post("/login", response_model=LoginOut)
async def login(payload: LoginIn, db: DbDep) -> LoginOut:
    email = payload.email.lower()
    user = await find_user_by_email(db, email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="邮箱未验证 · 请查收注册邮件或调用 /resend-verification",
        )
    return LoginOut(
        access_token=issue_access_token(user.id),
        user_id=str(user.id),
        email=user.email,
    )


@router.post("/verify", response_model=VerifyOut)
async def verify_email(payload: VerifyIn, db: DbDep) -> VerifyOut:
    user_id = await consume_verification_token(db, token=payload.token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证链接无效或已过期",
        )
    from app.services.auth import find_user_by_id  # 避免循环

    user = await find_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    user.email_verified_at = datetime.now(tz=UTC)
    await db.commit()
    return VerifyOut(verified=True, email=user.email)


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(payload: ResendIn, db: DbDep) -> dict[str, str]:
    """重发验证邮件 · 即使邮箱不存在也返回 202(防枚举攻击)。"""
    email = payload.email.lower()
    user = await find_user_by_email(db, email)
    if user is None or user.email_verified_at is not None:
        return {"status": "ok"}
    token = await create_verification_token(db, user_id=user.id)
    verify_url = f"{_public_base_url()}/verify-email?token={token}"
    try:
        await send_verification_email(to=email, verify_url=verify_url)
    except Exception:  # noqa: BLE001
        logger.exception("resend 邮件失败 email=%s", email)
    await db.commit()
    return {"status": "ok"}


@router.get("/me", response_model=MeOut)
async def me(current_user: CurrentUserDep) -> MeOut:
    return MeOut(
        user_id=str(current_user.id),
        email=current_user.email,
        email_verified=current_user.email_verified_at is not None,
    )
