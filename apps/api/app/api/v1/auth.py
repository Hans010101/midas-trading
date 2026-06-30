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
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.models.user import User
from app.services.auth import (
    consume_verification_token,
    create_verification_token,
    find_or_create_oauth_user,
    find_user_by_email,
    hash_password,
    issue_session,
    revoke_session,
    verify_password,
)
from app.services.email import send_verification_email
from app.services.growth import (
    attribute_invite,
    grant_trial_if_eligible,
    redeem_invite_if_pending,
)

# 复用同一个 scheme · auto_error=False 让未携带时也能进路由(我们自己处理)
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

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
    # Phase 1.5 刀A:邀请码归因(?ref= 透传)· 可选 · 无效码静默
    ref: str | None = Field(default=None, max_length=12)


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
    role: str = "user"


class VerifyIn(BaseModel):
    token: str


class VerifyOut(BaseModel):
    verified: bool
    email: str
    # Phase 1.5 刀A:前端感知(toast「试用已开通 / 邀请奖励已到账」)
    trial_granted: bool = False
    invite_rewarded: bool = False


class ResendIn(BaseModel):
    email: EmailStr


class MeOut(BaseModel):
    user_id: str
    email: str
    email_verified: bool
    role: str = "user"
    # 改密码 UI 分支:False = OAuth-only(无密码)→ 前端不显示改密码表单
    has_password: bool = False
    # 头像:NULL/0 = 默认首字母 · 1-16 = 预设头像
    avatar_id: int | None = None
    # 铂金标记(superadmin 手动设)· 前端据此显/隐铂金自助入口(PR-6 门控 · 真边界仍在后端 PlatinumDep)
    is_platinum: bool = False


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)  # 与注册同口径


class ChangePasswordOut(BaseModel):
    message: str = "密码已修改"


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

    # Phase 1.5 刀A:邀请归因(pending · 兑现等邮箱验证)· 整段静默不阻注册
    await attribute_invite(db, user.id, payload.ref)

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
async def login(payload: LoginIn, db: DbDep, request: Request) -> LoginOut:
    """邮箱密码登录 · 0006 ADR 2026-05-21 回归后返回 DB session token。

    响应字段名 access_token 保持不变(NextAuth 前端代码兼容)·
    实际是 opaque session token,不再是 JWT。
    """
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
    if user.banned_at is not None:  # 刀3b-2:封禁拒登(邮箱路)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被停用",
        )
    ua = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    session_token = await issue_session(
        db, user_id=user.id, user_agent=ua, ip_address=ip,
    )
    await db.commit()
    return LoginOut(
        access_token=session_token,
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )


class LogoutOut(BaseModel):
    ok: bool = True


@router.post("/logout", response_model=LogoutOut)
async def logout(
    db: DbDep,
    token: Annotated[str | None, Depends(_oauth2_scheme)],
) -> LogoutOut:
    """注销当前 session(失败也返回 ok=True · 客户端无感)。"""
    if token:
        await revoke_session(db, token=token)
        await db.commit()
    return LogoutOut()


# ============ Google OAuth · M1 第三波 ============


class OAuthGoogleIn(BaseModel):
    """前端 NextAuth Google provider 拿到 id_token / userinfo 后转发到这里。

    前端在 NextAuth `signIn` callback 里调本端点 · 用 backend service
    secret 头部认证 · 拿到 session token 后存 NextAuth cookie。
    """
    id_token: str = Field(min_length=10)  # Google ID Token JWT
    # Phase 1.5 刀A:邀请码归因(cookie 透传 · 仅 create 分支生效)
    ref: str | None = Field(default=None, max_length=12)


class OAuthGoogleOut(BaseModel):
    access_token: str  # opaque DB session token · 名字保留兼容前端
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str = "user"
    is_new_user: bool = False
    # Phase 1.5 刀A:前端感知
    trial_granted: bool = False
    invite_rewarded: bool = False


@router.post("/oauth/google", response_model=OAuthGoogleOut)
async def oauth_google(
    payload: OAuthGoogleIn, db: DbDep, request: Request,
) -> OAuthGoogleOut:
    """Google OAuth 登录 / 注册。

    流程:
    1. 验证 id_token(Google 公钥签名 · jose 解析)
    2. 提取 sub / email / email_verified
    3. find_or_create_oauth_user(google_sub, email) → User
    4. issue_session() → opaque DB session token
    5. 返回 access_token(跟密码登录一样的格式 · NextAuth 一视同仁)

    安全:
    - id_token 是 Google 签发的 JWT · 必须验签 + 验 aud(client_id 匹配)
    - 如果 client_id 不在 env 配置 · 返回 503(开关未开)
    """
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if not google_client_id:
        logger.error("[oauth.google] GOOGLE_CLIENT_ID 未配置 · 返回 503")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth 未启用(GOOGLE_CLIENT_ID 未配置)",
        )
    logger.info("[oauth.google] 收到 id_token · client_id 前 12 字符=%s", google_client_id[:12])

    # 验签 + 解析 · Google 公钥 JWKS
    # 注:_verify_google_id_token 会把 httpx / jose 错误都归类成 ValueError
    try:
        claims = await _verify_google_id_token(payload.id_token, google_client_id)
    except ValueError as e:
        logger.warning("[oauth.google] id_token 验证失败:%s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google id_token 验证失败:{e}",
        ) from e

    google_sub = cast(str, claims["sub"])
    email = cast(str, claims["email"])
    logger.info("[oauth.google] id_token 验签通过 · sub=%s email=%s", google_sub, email)

    if not claims.get("email_verified", False):
        logger.warning("[oauth.google] email_verified=false · 拒绝 · email=%s", email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Google 账号邮箱未验证",
        )

    # find_or_create + 发 session · DB 错误单独 catch · 暴露明细(常见:google_sub 列缺失)
    try:
        # Phase 1.5 刀A:created 以 find_or_create 内部标志为准(★ 按 sub 查的
        # existed_before 会把 email-linking 老用户误判为新 → 误送试用 + is_new 假阳)
        user, created = await find_or_create_oauth_user(
            db, google_sub=google_sub, email=email,
        )
        # 刀3b-2:封禁拒登(OAuth 路 · 已封禁的老 Google 用户重登被拒)。
        # created 用户刚建不可能 banned;HTTPException 在下方 except HTTPException 透传不被吞成 500。
        if user.banned_at is not None:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被停用",
            )
        trial_granted = False
        invite_rewarded = False
        if created:
            # Google 新建即 verified → 归因 + 试用 + 即时兑现(同 verify 路径顺序)
            await attribute_invite(db, user.id, payload.ref)
            trial_granted = await grant_trial_if_eligible(db, user.id)
            invite_rewarded = await redeem_invite_if_pending(db, user.id)

        ua = request.headers.get("user-agent")
        ip = request.client.host if request.client else None
        session_token = await issue_session(
            db, user_id=user.id, user_agent=ua, ip_address=ip,
        )
        await db.commit()
    except HTTPException:
        raise  # 刀3b-2:封禁 403 等业务异常原样透传,不被下方吞成 500
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.exception("[oauth.google] DB 写入失败(find_or_create / issue_session)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Google 登录建用户 / 发 session 失败:{type(e).__name__}: {e}",
        ) from e

    logger.info(
        "[oauth.google] 登录成功 · user_id=%s email=%s is_new=%s",
        user.id, user.email, created,
    )
    return OAuthGoogleOut(
        access_token=session_token,
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        is_new_user=created,  # 修复:linking 老用户原被误报 true(同 created 根因)
        trial_granted=trial_granted,
        invite_rewarded=invite_rewarded,
    )


# === Google id_token 验证 helper ===
# 用 httpx 拉 JWKS · jose 验签 · M1 第三波最小化 · M2+ 加缓存

_GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


async def _verify_google_id_token(
    token: str, expected_aud: str,
) -> dict[str, object]:
    """验签 Google id_token · 失败抛 ValueError。"""
    import httpx  # noqa: PLC0415
    from jose import jwt as jose_jwt  # noqa: PLC0415
    from jose.exceptions import JWTError  # noqa: PLC0415

    # 拉 Google 公钥(M1 不缓存 · 每次拉 · M2+ 改 LRU)
    # 网络错 / 非 2xx 都归类成 ValueError · 让上层返 401 带明细而不是裸 500
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(_GOOGLE_JWKS_URL)
            r.raise_for_status()
            jwks = r.json()
    except httpx.HTTPError as e:
        raise ValueError(
            f"拉 Google JWKS 失败({_GOOGLE_JWKS_URL}): {type(e).__name__}: {e}",
        ) from e

    try:
        # 不带签名解 header 拿 kid
        unverified_header = jose_jwt.get_unverified_header(token)
    except JWTError as e:
        raise ValueError(f"无法解析 token header: {e}") from e

    kid = unverified_header.get("kid")
    if not kid:
        raise ValueError("token 缺 kid")

    key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
    if key is None:
        raise ValueError(f"未找到 kid={kid} 对应的 Google 公钥")

    try:
        claims = jose_jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=expected_aud,
            issuer=_GOOGLE_ISSUERS,
            # NextAuth 走 id_token 流程 · 只把 id_token 转给后端 · 没有 access_token。
            # jose 默认 verify_at_hash=True · 检测到 id_token 里有 at_hash claim 但
            # 没传 access_token 就抛 "No access_token provided to compare against
            # at_hash claim" → 401。
            # at_hash 是「id_token 跟 access_token 绑定」的可选校验 · OIDC 规范里
            # 客户端可选做。我们后端只验签名 + aud + iss + exp(这些才是安全核心)·
            # 显式关掉 at_hash 校验。
            options={"verify_at_hash": False},
        )
    except JWTError as e:
        raise ValueError(str(e)) from e

    if "sub" not in claims or "email" not in claims:
        raise ValueError("token 缺 sub / email claim")
    return claims  # type: ignore[no-any-return]


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
    # Phase 1.5 刀A:★ trial 必须先于兑现(invite 先开行会让 trial 误判已有订阅)
    trial_granted = await grant_trial_if_eligible(db, user.id)
    invite_rewarded = await redeem_invite_if_pending(db, user.id)
    await db.commit()
    return VerifyOut(
        verified=True, email=user.email,
        trial_granted=trial_granted, invite_rewarded=invite_rewarded,
    )


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
        role=current_user.role,
        has_password=current_user.password_hash is not None,
        avatar_id=current_user.avatar_id,
        is_platinum=current_user.is_platinum,
    )


@router.post("/change-password", response_model=ChangePasswordOut)
async def change_password(
    payload: ChangePasswordIn, current_user: CurrentUserDep, db: DbDep,
) -> ChangePasswordOut:
    """修改密码(邮箱密码用户)· 旧密码校验通过后写入新 hash。

    🔴 OAuth-only 用户(password_hash=None)→ 409 拒(账户安全由 Google 管理)· 前端也不显示表单。
    复用 verify_password / hash_password · 密码明文绝不进日志/返回/异常。
    TODO(M1+ 安全):改密后是否 revoke_all_user_sessions 其它设备下线 · 本期不做(避免复杂化)。
    """
    if current_user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="你通过 Google 登录,账户安全由 Google 管理,无需在此修改密码",
        )
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误",
        )
    current_user.password_hash = hash_password(payload.new_password)
    await db.commit()
    logger.info("[change-password] user_id=%s 改密成功", current_user.id)  # 不记明文
    return ChangePasswordOut()
