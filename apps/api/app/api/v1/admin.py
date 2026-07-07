"""管理员 · 用户管理 API(用户管理刀1 · 纯只读)。

🔴 安全边界:每个端点必挂 AdminDep(后端 403 强制)—— 前端藏菜单/middleware
   只是 UX 层,不是边界。新增端点时 AdminDep 一个不许漏(pytest 403 矩阵钉死)。
🔴 红线:本文件零写操作 · 交易链路零碰。

口径说明:
- last_active_7d:该用户未过期 session 的 MAX(last_used_at)。session 是 7 天
  滚动 TTL(过期即不算),所以「最后活跃」只覆盖最近 7 天,更早 → null。
- active_sessions:未过期 session 数(≈ 在线设备数,上限 5)。
- register_method:由 google_sub / password_hash 非空推导(google|password|both)。
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep, ClickHouseDep
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.admin_action_log import AdminActionLog
from app.models.daily_crawler_stat import DailyCrawlerStat
from app.models.daily_referrer_stat import DailyReferrerStat
from app.models.daily_source_stat import DailySourceStat
from app.models.daily_visit_stat import DailyVisitStat
from app.models.platform_dispatch import PlatformDispatch
from app.models.redeem_code import RedeemCode
from app.models.session import Session
from app.models.subscription import Subscription
from app.models.user import User
from app.models.weekly_dispatch import WeeklyDispatch
from app.models.x_tweet import XTweet
from app.schemas.report import (
    MaterialListOut,
    MaterialOut,
    ReportDetail,
    ReportListItem,
    ReportListOut,
    ReportSendOut,
    ReportUpdateIn,
)
from app.schemas.weekly_dispatch import (
    WeeklyDispatchDetail,
    WeeklyDispatchList,
    WeeklyDispatchListItem,
    WeeklySendOut,
    WeeklyUploadOut,
)
from app.services.academy.admin_stats import get_academy_stats
from app.services.growth import extend_subscription, invite_stats
from app.services.membership import PLAN_QUOTAS, get_quota_used, resolve_plan
from app.services.report import materials as report_materials
from app.services.report import store as report_store
from app.services.report import weekly_dispatch as wd_service
from app.services.report.generate import current_report_period, generate_weekly_report_draft
from app.services.report.materials import MaterialExtractError
from app.services.report.object_store import ObjectStoreError
from app.services.report.send import send_report
from app.services.report.weekly_dispatch import UNSUBSCRIBE_URL
from app.services.report.weekly_email import render_email_html
from app.services.report.weekly_md import WeeklyMdError
from app.services.visit_stats import (
    CN_TZ,
    cn_today,
    read_redis_crawler_day,
    read_redis_day,
    read_redis_hours,
    read_redis_referrer_day,
    read_redis_source_day,
)
from app.services.x_marketing.compliance import has_body_url
from app.services.x_marketing.generate import enqueue_daily_generation
from app.services.x_marketing.publish import auto_guard
from app.services.x_marketing.publish.dispatch import enqueue_publish, revoke_auto_tasks
from app.services.x_marketing.publish.rate_limit import check_rate
from app.services.x_marketing.publish.registry import get_adapter
from app.services.x_marketing.publish.store import (
    get_dispatch,
    list_dispatches,
    list_dispatches_for_tweets,
    upsert_pending,
)
from app.services.x_marketing.store import get_tweet, list_recent

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]


class AdminUserItem(BaseModel):
    id: str
    email: str
    role: str
    banned: bool  # 刀3b-2:已停用
    plan: str  # 会员刀2:free / pro(subscription outerjoin 批量解析 · 防 N+1)
    is_platinum: bool  # ★铂金标记(多账户 PR-1)· superadmin 手动设 · 享受所有 pro 权益
    created_at: datetime
    email_verified: bool
    register_method: str  # google | password | both
    last_active_7d: datetime | None
    active_sessions: int


class AdminUserListOut(BaseModel):
    items: list[AdminUserItem]
    total: int
    page: int
    page_size: int


def _register_method(google_sub: str | None, password_hash: str | None) -> str:
    if google_sub is not None and password_hash is not None:
        return "both"
    return "google" if google_sub is not None else "password"


@router.get("/users", response_model=AdminUserListOut)
async def list_users(
    _admin: AdminDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUserListOut:
    """用户列表(分页 · created_at desc)· session 聚合一条 outerjoin 防 N+1。"""
    now = datetime.now(UTC)
    # 订阅行 outerjoin(每用户至多一行 unique)· Python 侧三态判定 → 零 N+1
    # (口径与 services.membership.resolve_plan 一致:非 active / 过期 / 未知 → free)
    sub = Subscription.__table__.alias("sub")
    # 未过期 session 按 user 聚合(7 天滚动 TTL → last_active 天然 7d 口径)
    sess_agg = (
        select(
            Session.user_id,
            func.max(Session.last_used_at).label("last_active"),
            func.count(Session.id).label("session_count"),
        )
        .where(Session.expires_at > now)
        .group_by(Session.user_id)
        .subquery()
    )

    rows = (
        await db.execute(
            select(
                User,
                sess_agg.c.last_active,
                sess_agg.c.session_count,
                sub.c.plan,
                sub.c.status,
                sub.c.expires_at,
            )
            .outerjoin(sess_agg, sess_agg.c.user_id == User.id)
            .outerjoin(sub, sub.c.user_id == User.id)
            # created_at 平局 → id tie-break(分页稳定 · 铁律 · 同 conditional/backtest)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size),
        )
    ).all()
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()

    def _plan_of(
        plan: str | None, sub_status: str | None, expires_at: datetime | None, *,
        is_platinum: bool,
    ) -> str:
        if is_platinum:  # ★铂金标记 → pro(与 resolve_plan 一致 · 管理员列表口径对齐实际)
            return "pro"
        if plan is None or sub_status != "active":
            return "free"
        if expires_at is not None and expires_at <= now:
            return "free"
        return plan if plan in PLAN_QUOTAS else "free"

    return AdminUserListOut(
        items=[
            AdminUserItem(
                id=str(u.id),
                email=u.email,
                role=u.role,
                banned=u.banned_at is not None,
                plan=_plan_of(plan, sub_status, expires_at, is_platinum=u.is_platinum),
                is_platinum=u.is_platinum,
                created_at=u.created_at,
                email_verified=u.email_verified_at is not None,
                register_method=_register_method(u.google_sub, u.password_hash),
                last_active_7d=last_active,
                active_sessions=session_count or 0,
            )
            for u, last_active, session_count, plan, sub_status, expires_at in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── 用户详情(刀3a · 纯只读聚合)─────────────────────────────────────────────


class QuotaUsage(BaseModel):
    feature: str
    used: int | None  # Redis 故障 → None(前端显 "—")
    limit: int


class RedeemedItem(BaseModel):
    code: str
    period: str
    redeemed_at: datetime


class AdminActionItem(BaseModel):
    action: str
    detail: dict[str, object]
    created_at: datetime


class AdminUserDetail(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime
    email_verified: bool
    banned: bool  # 刀3b-2:已停用
    # 会员
    plan: str
    is_platinum: bool  # ★铂金标记(多账户 PR-1)· superadmin 手动设 · 享受所有 pro 权益
    plan_status: str | None
    plan_expires_at: datetime | None
    plan_source: str | None
    quota: list[QuotaUsage]  # 今日额度用量
    invite_code: str | None  # 邀请
    invited_count: int
    rewarded_count: int
    redeemed: list[RedeemedItem]  # 兑换记录
    admin_actions: list[AdminActionItem]  # 刀3b:该用户被调权益/操作历史


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user_detail(user_id: str, _admin: AdminDep, db: DbDep) -> AdminUserDetail:
    """单用户详情聚合 · 纯只读(不改任何状态 · 写操作留刀3b)。

    防 N+1:每块独立单查询(user / subscription / invitation 聚合 / redeem_code),
    无循环查;额度走 Redis(故障 None 不报错)。
    """
    try:
        uid = UUID(user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在") from e

    user = await db.scalar(select(User).where(User.id == uid))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    plan = await resolve_plan(db, uid)
    sub = await db.scalar(select(Subscription).where(Subscription.user_id == uid))

    # 额度(今日 · Redis 故障 → used=None)
    quota: list[QuotaUsage] = []
    for feature in ("diagnose", "backtest"):
        try:
            used: int | None = await get_quota_used(uid, feature)
        except Exception:  # noqa: BLE001 — Redis 故障不阻塞详情
            used = None
        quota.append(QuotaUsage(feature=feature, used=used, limit=PLAN_QUOTAS[plan][feature]))

    invited, rewarded = await invite_stats(db, uid)

    # 该用户兑换过的码(redeemed_by=uid · 单查询)
    redeemed_rows = (
        await db.execute(
            select(RedeemCode.code, RedeemCode.period, RedeemCode.redeemed_at)
            .where(RedeemCode.redeemed_by == uid)
            .order_by(RedeemCode.redeemed_at.desc()),
        )
    ).all()

    # 该用户的管理员操作历史(target=uid · 单查询 · 刀3b)
    action_rows = (
        await db.execute(
            select(AdminActionLog.action, AdminActionLog.detail, AdminActionLog.created_at)
            .where(AdminActionLog.target_user_id == uid)
            .order_by(AdminActionLog.created_at.desc()),
        )
    ).all()

    return AdminUserDetail(
        id=str(user.id),
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        email_verified=user.email_verified_at is not None,
        banned=user.banned_at is not None,
        plan=plan,
        is_platinum=user.is_platinum,
        plan_status=sub.status if sub else None,
        plan_expires_at=sub.expires_at if sub else None,
        plan_source=sub.source if sub else None,
        quota=quota,
        invite_code=user.invite_code,
        invited_count=invited,
        rewarded_count=rewarded,
        redeemed=[
            RedeemedItem(code=c, period=p, redeemed_at=ra)
            for c, p, ra in redeemed_rows
            if ra is not None
        ],
        admin_actions=[
            AdminActionItem(action=a, detail=d, created_at=ca)
            for a, d, ca in action_rows
        ],
    )


# ── 管理员手动调权益(刀3b-1 · 写操作)─────────────────────────────────────
# 🔴 只写 subscription + admin_action_log;不碰 engine/login;operator 取自鉴权。

_GRANT_MAX_DAYS = 3650  # 单次授予上限 10 年(防误操作打错巨值)
_PERIOD_TO_DAYS = {"month": 30, "quarter": 90, "year": 365}


class GrantIn(BaseModel):
    # 二选一:period(月/季/年)或 days(直接天数)· 都给以 days 优先
    period: str | None = None
    days: int | None = Field(default=None, ge=1, le=_GRANT_MAX_DAYS)
    note: str | None = Field(default=None, max_length=200)


class GrantOut(BaseModel):
    plan: str
    expires_at: datetime | None
    days_added: int


@router.post("/users/{user_id}/grant", response_model=GrantOut)
async def grant_pro(user_id: str, payload: GrantIn, admin: AdminDep, db: DbDep) -> GrantOut:
    """管理员授予/延长 Pro(source='admin' · 不封顶)+ 审计 · 同事务。

    operator = 当前 admin(AdminDep · ★ 不信前端传入);目标不存在 404;天数非法 422。
    """
    try:
        uid = UUID(user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在") from e

    # 解析天数:days 优先,否则 period 映射
    days = payload.days
    if days is None and payload.period is not None:
        days = _PERIOD_TO_DAYS.get(payload.period)
    if days is None or days <= 0 or days > _GRANT_MAX_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="天数非法(需 period=month|quarter|year 或 1..3650 的 days)",
        )

    target = await db.scalar(select(User).where(User.id == uid))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 授予权益与写审计在同一事务(任一失败整体回滚)。
    new_exp = await extend_subscription(db, uid, days, "admin")  # 不传 cap_days = 不封顶
    db.add(AdminActionLog(
        operator_id=admin.id,  # ★ 取自鉴权,绝不信前端
        target_user_id=uid,
        action="grant_pro",
        detail={"days": days, "period": payload.period, "note": payload.note},
    ))
    await db.commit()
    return GrantOut(plan="pro", expires_at=new_exp, days_added=days)


# ── 封禁 / 解封(刀3b-2 · 写操作 · 方案A 禁止登录)──────────────────────────
# 🔴 本刀唯一动登录链:user.banned_at + login/get_current_user 加检查(deps/auth.py)。
# 不能自封;operator 取鉴权;封禁+审计同事务。


class BanIn(BaseModel):
    note: str | None = Field(default=None, max_length=200)


class BanOut(BaseModel):
    user_id: str
    banned: bool


async def _set_ban(
    user_id: str, admin: User, db: AsyncSession, *, ban: bool, note: str | None,
) -> BanOut:
    try:
        uid = UUID(user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在") from e
    # ★ 不能自封(防把自己锁死)
    if ban and uid == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能停用自己",
        )
    target = await db.scalar(select(User).where(User.id == uid))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    target.banned_at = datetime.now(UTC) if ban else None
    db.add(AdminActionLog(
        operator_id=admin.id,  # ★ 取自鉴权,绝不信前端
        target_user_id=uid,
        action="ban" if ban else "unban",
        detail={"note": note},
    ))
    await db.commit()
    return BanOut(user_id=str(uid), banned=ban)


@router.post("/users/{user_id}/ban", response_model=BanOut)
async def ban_user(user_id: str, payload: BanIn, admin: AdminDep, db: DbDep) -> BanOut:
    return await _set_ban(user_id, admin, db, ban=True, note=payload.note)


@router.post("/users/{user_id}/unban", response_model=BanOut)
async def unban_user(user_id: str, payload: BanIn, admin: AdminDep, db: DbDep) -> BanOut:
    return await _set_ban(user_id, admin, db, ban=False, note=payload.note)


# ── 铂金标记(多账户 PR-1)· superadmin 手动设 · 仿 ban 范式 ──────────────────────
class PlatinumIn(BaseModel):
    is_platinum: bool  # ★服务端定·★不信前端传 user_id(从路径 + 鉴权)
    note: str | None = Field(default=None, max_length=200)


class PlatinumOut(BaseModel):
    user_id: str
    is_platinum: bool


@router.post("/users/{user_id}/set-platinum", response_model=PlatinumOut)
async def set_platinum(
    user_id: str, payload: PlatinumIn, admin: AdminDep, db: DbDep,
) -> PlatinumOut:
    """★superadmin 给/收用户铂金标记(享受所有 pro 权益 + 后续 3 功能)· 仿 ban_user 范式。

    🔴 AdminDep(只 superadmin)· operator 取自鉴权绝不信前端 · target 从路径 user_id ·
    is_platinum 值服务端按 payload 落库 · AdminActionLog 审计。
    """
    try:
        uid = UUID(user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在") from e
    target = await db.scalar(select(User).where(User.id == uid))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    target.is_platinum = payload.is_platinum
    db.add(AdminActionLog(
        operator_id=admin.id,  # ★ 取自鉴权,绝不信前端
        target_user_id=uid,
        action="set_platinum" if payload.is_platinum else "unset_platinum",
        detail={"is_platinum": payload.is_platinum, "note": payload.note},
    ))
    await db.commit()
    return PlatinumOut(user_id=str(uid), is_platinum=payload.is_platinum)


# ── 网站访问看板(PV/UV 趋势 + 注册趋势)· AdminDep · 纯只读 ──────────────────────
# 访问数据自上线起累积、历史不可回溯(部署前无访问日志);注册数据可回溯(user.created_at)。
# PV/UV:PG daily_visit_stat 历史 + Redis 今/昨实时叠加(不等下次 flush)。隐私:仅匿名计数。


class VisitDailyPoint(BaseModel):
    date: str  # ISO yyyy-mm-dd(CN 日)
    pv: int
    uv: int


class VisitHourlyPoint(BaseModel):
    hour: int  # 0-23(CST)
    pv: int
    uv: int


class RegistrationPoint(BaseModel):
    date: str
    count: int


class VisitStatsOut(BaseModel):
    range_days: int
    daily: list[VisitDailyPoint]  # 近 N 天 PV/UV(含今日实时)
    hourly: list[VisitHourlyPoint]  # ★当天 24 小时分布(Redis 实时 · 看高峰时段 · 上线后渐满)
    registrations: list[RegistrationPoint]  # 近 N 天每日注册数(user.created_at 回溯)
    today: VisitDailyPoint
    yesterday: VisitDailyPoint
    cumulative_pv: int  # 累计 PV(全历史 · 含今日实时)
    cumulative_uv: int  # 累计 UV = 各天 UV 之和(跨天不可去重 · 口径=每日 UV 累加)
    total_registrations: int  # 累计注册用户数(全历史)


def _empty(d: date_type) -> VisitDailyPoint:
    return VisitDailyPoint(date=d.isoformat(), pv=0, uv=0)


@router.get("/visit-stats", response_model=VisitStatsOut)
async def visit_stats(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
) -> VisitStatsOut:
    """访问看板取数 · PV/UV 日趋势(PG 历史 + Redis 今/昨实时)+ 注册日趋势(可回溯)。"""
    today = cn_today()
    yest = today - timedelta(days=1)
    start = today - timedelta(days=days - 1)

    # ① PV/UV:PG daily_visit_stat 历史(窗口内)
    rows = (
        await db.execute(
            select(DailyVisitStat.date, DailyVisitStat.pv, DailyVisitStat.uv)
            .where(DailyVisitStat.date >= start)
            .order_by(DailyVisitStat.date)
        )
    ).all()
    pg_map: dict[date_type, tuple[int, int]] = {r.date: (int(r.pv), int(r.uv)) for r in rows}
    today_pg = pg_map.get(today, (0, 0))

    # 叠加 Redis 今/昨实时(取 max 防回退);记今日实时增量用于累计补足
    redis = await get_redis()
    live_map = dict(pg_map)
    today_live = today_pg
    for d in (today, yest):
        if d < start:
            continue
        rpv, ruv = await read_redis_day(redis, d)
        bpv, buv = live_map.get(d, (0, 0))
        merged = (max(bpv, rpv), max(buv, ruv))
        live_map[d] = merged
        if d == today:
            today_live = merged

    daily = [
        VisitDailyPoint(
            date=(start + timedelta(days=i)).isoformat(),
            pv=live_map.get(start + timedelta(days=i), (0, 0))[0],
            uv=live_map.get(start + timedelta(days=i), (0, 0))[1],
        )
        for i in range(days)
    ]
    today_pt = VisitDailyPoint(date=today.isoformat(), pv=today_live[0], uv=today_live[1])
    yest_pt = VisitDailyPoint(
        date=yest.isoformat(),
        pv=live_map.get(yest, (0, 0))[0],
        uv=live_map.get(yest, (0, 0))[1],
    )

    # ② 累计 PV/UV(全历史 PG sum + 今日实时增量补足,因 flush 有 ≤10min 延迟)
    cum = (
        await db.execute(
            select(
                func.coalesce(func.sum(DailyVisitStat.pv), 0),
                func.coalesce(func.sum(DailyVisitStat.uv), 0),
            )
        )
    ).one()
    cumulative_pv = int(cum[0]) - today_pg[0] + today_live[0]
    cumulative_uv = int(cum[1]) - today_pg[1] + today_live[1]

    # ③ 注册趋势:user.created_at 按 CN 日聚合(窗口内 · 零填充缺失天)
    reg_day = func.date(func.timezone("Asia/Shanghai", User.created_at)).label("d")
    start_dt = datetime(start.year, start.month, start.day, tzinfo=CN_TZ)
    reg_rows = (
        await db.execute(
            select(reg_day, func.count().label("c"))
            .where(User.created_at >= start_dt)
            .group_by(reg_day)
            .order_by(reg_day)
        )
    ).all()
    reg_map = {
        (r.d.isoformat() if hasattr(r.d, "isoformat") else str(r.d)): int(r.c) for r in reg_rows
    }
    registrations = [
        RegistrationPoint(
            date=(start + timedelta(days=i)).isoformat(),
            count=reg_map.get((start + timedelta(days=i)).isoformat(), 0),
        )
        for i in range(days)
    ]
    total_reg = (await db.execute(select(func.count()).select_from(User))).scalar() or 0

    # ④ 当天 24 小时分布(Redis 实时 · 上线后渐满 · 历史天不回溯)
    hours = await read_redis_hours(redis, today)
    hourly = [
        VisitHourlyPoint(hour=h, pv=hours[h][0], uv=hours[h][1]) for h in range(24)
    ]

    return VisitStatsOut(
        range_days=days,
        daily=daily,
        hourly=hourly,
        registrations=registrations,
        today=today_pt,
        yesterday=yest_pt,
        cumulative_pv=cumulative_pv,
        cumulative_uv=cumulative_uv,
        total_registrations=int(total_reg),
    )


# ── SEO 批6 · 流量来源归因 + AI 爬虫看板(AdminDep · 独立端点 · 不动 visit-stats)──────
# ★独立 SourceStatsOut + 独立三表聚合,绝不改 VisitStatsOut(不碰其测试)。
# ★D8 口径:只读来源桶/来源域名/爬虫按天聚合 · 无 IP/UA/个体明细。窗口内 PG 历史 +
#   今/昨 Redis 实时叠加(同 visit-stats 的 max-per-day 防回退,避免 flush ≤10min 延迟漏计)。


class SourceCount(BaseModel):
    source: str
    pv: int


class CrawlerCount(BaseModel):
    bot: str
    hits: int


class ReferrerCount(BaseModel):
    referrer: str
    pv: int


class SourceStatsOut(BaseModel):
    range_days: int
    sources: list[SourceCount]          # 各来源桶总 PV(降序 · 含今/昨实时)
    crawlers: list[CrawlerCount]        # 各 bot 总 hits(降序 · 含今/昨实时 · GEO 领先指标)
    top_referrers: list[ReferrerCount]  # top 来源域名(降序 · 上限 50)
    total_attributed_pv: int            # 有来源归因的总 PV(= sources 之和)


async def _agg_with_live(
    rows: Sequence[Any],
    redis: Any,
    read_live: Callable[[Any, date_type], Awaitable[dict[str, int]]],
    *,
    start: date_type,
    today: date_type,
    yest: date_type,
) -> dict[str, int]:
    """纯聚合:PG 每 (dim, date, count) 行 + 今/昨 Redis 实时 max 叠加 → {dim: total}。

    caller 各自建 typed select(具体列 · mypy 友好)· 本函数不碰 SQLAlchemy 只做累加。
    """
    per_day: dict[tuple[date_type, str], int] = {
        (r[1], str(r[0])): int(r[2]) for r in rows  # (date, dim): count
    }
    for d in (today, yest):
        if d < start:
            continue
        for dim, cnt in (await read_live(redis, d)).items():
            key = (d, dim)
            per_day[key] = max(per_day.get(key, 0), int(cnt))
    totals: dict[str, int] = {}
    for (_d, dim), cnt in per_day.items():
        totals[dim] = totals.get(dim, 0) + cnt
    return totals


@router.get("/source-stats", response_model=SourceStatsOut)
async def source_stats(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
) -> SourceStatsOut:
    """流量来源看板:各来源桶 PV + AI/搜索爬虫计数 + top 来源域名(窗口内 · 含今/昨实时)。"""
    today = cn_today()
    yest = today - timedelta(days=1)
    start = today - timedelta(days=days - 1)
    redis = await get_redis()

    src_rows = (
        await db.execute(
            select(DailySourceStat.source, DailySourceStat.date, DailySourceStat.pv)
            .where(DailySourceStat.date >= start)
        )
    ).all()
    src_totals = await _agg_with_live(
        src_rows, redis, read_redis_source_day, start=start, today=today, yest=yest,
    )
    crawler_rows = (
        await db.execute(
            select(DailyCrawlerStat.bot, DailyCrawlerStat.date, DailyCrawlerStat.hits)
            .where(DailyCrawlerStat.date >= start)
        )
    ).all()
    crawler_totals = await _agg_with_live(
        crawler_rows, redis, read_redis_crawler_day, start=start, today=today, yest=yest,
    )
    ref_rows = (
        await db.execute(
            select(DailyReferrerStat.referrer, DailyReferrerStat.date, DailyReferrerStat.pv)
            .where(DailyReferrerStat.date >= start)
        )
    ).all()
    ref_totals = await _agg_with_live(
        ref_rows, redis, read_redis_referrer_day, start=start, today=today, yest=yest,
    )

    sources = [
        SourceCount(source=s, pv=c)
        for s, c in sorted(src_totals.items(), key=lambda kv: kv[1], reverse=True)
    ]
    crawlers = [
        CrawlerCount(bot=b, hits=c)
        for b, c in sorted(crawler_totals.items(), key=lambda kv: kv[1], reverse=True)
    ]
    top_referrers = [
        ReferrerCount(referrer=r, pv=c)
        for r, c in sorted(ref_totals.items(), key=lambda kv: kv[1], reverse=True)[:50]
    ]
    return SourceStatsOut(
        range_days=days,
        sources=sources,
        crawlers=crawlers,
        top_referrers=top_referrers,
        total_attributed_pv=sum(src_totals.values()),
    )


# ── 训练营「答题赢会员」统计(刀4)· AdminDep · 纯只读聚合 academy 三表 ──────────────
# 总览(全历史)+ 各模块分布(全历史)+ 发会员/提交每日趋势(近 N 天)· 不碰发放逻辑/交易/支付。


class AcademyStageStatOut(BaseModel):
    stage: str
    learners: int      # 学完人数(distinct user)
    submissions: int   # 结业测验提交数
    passers: int       # 达标人数(distinct user)
    awards: int        # 发会员人次


class AcademyDayPoint(BaseModel):
    date: str
    count: int


class AcademyStatsOut(BaseModel):
    range_days: int
    learner_count: int            # 有学习记录人数
    total_awards: int             # 总发会员人次
    membership_days_granted: int  # 送出会员天数 = 总发会员人次 × 7
    total_submissions: int        # 结业测验总提交
    pass_rate: float              # 整体通过率(0~1)
    by_stage: list[AcademyStageStatOut]
    award_trend: list[AcademyDayPoint]
    submission_trend: list[AcademyDayPoint]


@router.get("/academy-stats", response_model=AcademyStatsOut)
async def academy_stats(
    _admin: AdminDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
) -> AcademyStatsOut:
    """训练营统计取数 · ★AdminDep(403)· 纯只读聚合三表。"""
    s = await get_academy_stats(db, days=days)
    return AcademyStatsOut(
        range_days=s.range_days,
        learner_count=s.learner_count,
        total_awards=s.total_awards,
        membership_days_granted=s.membership_days_granted,
        total_submissions=s.total_submissions,
        pass_rate=s.pass_rate,
        by_stage=[
            AcademyStageStatOut(
                stage=x.stage,
                learners=x.learners,
                submissions=x.submissions,
                passers=x.passers,
                awards=x.awards,
            )
            for x in s.by_stage
        ],
        award_trend=[AcademyDayPoint(date=p.date, count=p.count) for p in s.award_trend],
        submission_trend=[
            AcademyDayPoint(date=p.date, count=p.count) for p in s.submission_trend
        ],
    )


# ════════════════════════════════════════════════════════════════════════════
# 市场周报复核(P2)· 🔴 每端点挂 AdminDep · draft → approved(★发送是第二刀,本刀不做)
# ════════════════════════════════════════════════════════════════════════════
@router.get("/reports", response_model=ReportListOut)
async def list_market_reports(
    _admin: AdminDep,
    db: DbDep,
    status_filter: str | None = Query(
        None, alias="status", description="按状态筛 draft/approved/sent",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ReportListOut:
    rows, total = await report_store.list_reports(
        db, status=status_filter, limit=limit, offset=offset,
    )
    return ReportListOut(
        items=[ReportListItem.model_validate(r) for r in rows],
        total=total,
    )


@router.get("/reports/{report_id}", response_model=ReportDetail)
async def get_market_report(report_id: int, _admin: AdminDep, db: DbDep) -> ReportDetail:
    report = await report_store.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return ReportDetail.model_validate(report)


@router.put("/reports/{report_id}", response_model=ReportDetail)
async def update_market_report(
    report_id: int, payload: ReportUpdateIn, _admin: AdminDep, db: DbDep,
) -> ReportDetail:
    """编辑报告 title/content(内容立项前 admin 也能手动填专业内容测试)· 已发送不可改(409)。"""
    try:
        report = await report_store.update_report(
            db, report_id, title=payload.title, content=payload.content,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return ReportDetail.model_validate(report)


@router.post("/reports/{report_id}/approve", response_model=ReportDetail)
async def approve_market_report(report_id: int, admin: AdminDep, db: DbDep) -> ReportDetail:
    """批准报告(draft → approved · approved_by 取鉴权)· 非 draft 拒(409)。本刀不发送。"""
    try:
        report = await report_store.approve_report(db, report_id, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return ReportDetail.model_validate(report)


@router.post(
    "/reports/generate", response_model=ReportDetail, status_code=status.HTTP_201_CREATED,
)
async def generate_market_report_now(
    _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ReportDetail:
    """★手动触发生成一篇周报草稿(测试用 · 不必等周一 beat)· 与 Celery 任务共用同一生成逻辑。"""
    report = await generate_weekly_report_draft(db, ch)
    return ReportDetail.model_validate(report)


@router.post("/reports/{report_id}/send", response_model=ReportSendOut)
async def send_market_report(
    report_id: int, _admin: AdminDep, db: DbDep,
) -> ReportSendOut:
    """★人工发布:approved 报告 → 邮件(全文+PDF)+ TG/飞书提示发给订阅用户 → status=sent。

    ★只 approved 可发(draft/sent → 409)· 不存在 → 404 · ★广播失败逐人隔离(部分失败不整体崩)。
    早期同步发送(订阅量小)· 量大可平移 Celery(逻辑已在 services/report/send)。
    """
    try:
        result = await send_report(db, report_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在") from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return ReportSendOut(
        report_id=result.report_id,
        status="sent",
        recipients=result.recipients,
        email_sent=result.email_sent,
        email_failed=result.email_failed,
        notify_sent=result.notify_sent,
        notify_failed=result.notify_failed,
    )


# 周报素材(第三刀)· admin 上传 md/PDF 外部素材 → 提取文本注入生成
# ★路径用 /report-materials(非 /reports/materials):后者会被 GET /reports/{report_id} 先匹配,
#   "materials" 被当 report_id 校验为 int → 422。独立路径避开路由顺序碰撞,更稳。
_MATERIAL_MAX_MB = 10
_MATERIAL_MAX_BYTES = _MATERIAL_MAX_MB * 1024 * 1024


@router.post(
    "/report-materials", response_model=MaterialOut, status_code=status.HTTP_201_CREATED,
)
async def upload_report_material(
    admin: AdminDep,
    db: DbDep,
    file: Annotated[UploadFile, File()],
) -> MaterialOut:
    """admin 上传周报素材(md / PDF · multipart)→ 提取文本存库 + 原始文件存 OSS(标记本期周期)。

    镜像 support 上传范式 · 提取失败 / 不支持 → 422 · ★OSS 上传失败(凭证缺失/网络)→ 502(不静默)。
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="文件为空")
    if len(data) > _MATERIAL_MAX_BYTES:
        raise HTTPException(
            status_code=422, detail=f"素材文件不得超过 {_MATERIAL_MAX_MB} MB",
        )
    period_start, period_end = current_report_period()
    try:
        material = await report_materials.create_material(
            db,
            filename=file.filename or "material",
            content_type=file.content_type,
            data=data,
            period_start=period_start,
            period_end=period_end,
            uploaded_by=admin.id,
        )
    except MaterialExtractError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ObjectStoreError as e:
        # OSS 上传失败(凭证未配 / 网络)· 502 上游存储错误 · 详情已 log(不含凭证)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"素材存储失败:{e}",
        ) from e
    return MaterialOut.model_validate(material)


@router.get("/report-materials", response_model=MaterialListOut)
async def list_report_materials(_admin: AdminDep, db: DbDep) -> MaterialListOut:
    """列本期素材(按当前周报周期 · created_at 倒序)。"""
    period_start, period_end = current_report_period()
    rows = await report_materials.list_materials(db, period_start=period_start)
    return MaterialListOut(
        items=[MaterialOut.model_validate(r) for r in rows],
        period_start=period_start,
        period_end=period_end,
    )


@router.delete("/report-materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report_material(material_id: int, _admin: AdminDep, db: DbDep) -> None:
    """删一份素材(手动)· 不存在 → 404 · OSS 对象靠桶 lifecycle,此处不删 OSS。"""
    ok = await report_materials.delete_material(db, material_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材不存在")


# 周报投递(全自动发送)· 运营上传成品 PDF+md → 提取 → 定时/补传发送
_WD_PDF_MAX_MB = 20
_WD_PDF_MAX_BYTES = _WD_PDF_MAX_MB * 1024 * 1024


@router.post(
    "/weekly-dispatch/upload", response_model=WeeklyUploadOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_weekly_dispatch(
    admin: AdminDep,
    db: DbDep,
    pdf: Annotated[UploadFile, File()],
    md: Annotated[UploadFile, File()],
) -> WeeklyUploadOut:
    """上传成品周报(PDF + md)→ 解析 md → PDF 存 OSS → upsert(status=uploaded)。

    ★frontmatter 错 → 422 · OSS 失败 → 502 · ★上传只入库 uploaded,不自动发(需人工点计划/立即发送)。
    """
    pdf_data = await pdf.read()
    md_data = await md.read()
    if not pdf_data or not md_data:
        raise HTTPException(status_code=422, detail="PDF 与 md 文件都必须上传且非空")
    if len(pdf_data) > _WD_PDF_MAX_BYTES:
        raise HTTPException(status_code=422, detail=f"PDF 不得超过 {_WD_PDF_MAX_MB} MB")
    md_text = md_data.decode("utf-8", errors="replace")
    try:
        rec, _extract = await wd_service.create_or_update_dispatch(
            db,
            pdf_data=pdf_data,
            pdf_filename=(pdf.filename or "周报.pdf")[:255],
            md_text=md_text,
            uploaded_by=admin.id,
        )
    except WeeklyMdError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ObjectStoreError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"PDF 存储失败:{e}",
        ) from e

    email_html = render_email_html(rec.extracted, unsubscribe_url=UNSUBSCRIBE_URL)
    return WeeklyUploadOut(
        id=rec.id, year=rec.year, week=rec.week, status=rec.status,
        extracted=rec.extracted, missing=rec.extracted.get("missing", []),
        email_html=email_html, pdf_filename=rec.pdf_filename,
    )


def _weekly_detail(rec: WeeklyDispatch) -> WeeklyDispatchDetail:
    """WeeklyDispatch 行 → 详情(含邮件 HTML 预览)· schedule/cancel/detail 端点共用。"""
    return WeeklyDispatchDetail(
        id=rec.id, year=rec.year, week=rec.week,
        period_start=rec.period_start, period_end=rec.period_end,
        title=rec.title, status=rec.status, pdf_filename=rec.pdf_filename,
        uploaded_at=rec.uploaded_at, sent_at=rec.sent_at,
        extracted=rec.extracted,
        email_html=render_email_html(rec.extracted, unsubscribe_url=UNSUBSCRIBE_URL),
        next_send_label=wd_service.current_next_send_label(),
    )


@router.get("/weekly-dispatch", response_model=WeeklyDispatchList)
async def list_weekly_dispatches(_admin: AdminDep, db: DbDep) -> WeeklyDispatchList:
    rows = await wd_service.list_dispatches(db)
    return WeeklyDispatchList(
        items=[WeeklyDispatchListItem.model_validate(r) for r in rows],
        next_send_label=wd_service.current_next_send_label(),
    )


@router.get("/weekly-dispatch/{dispatch_id}", response_model=WeeklyDispatchDetail)
async def get_weekly_dispatch(
    dispatch_id: int, _admin: AdminDep, db: DbDep,
) -> WeeklyDispatchDetail:
    rec = await wd_service.get_dispatch(db, dispatch_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="周报投递不存在")
    return _weekly_detail(rec)


@router.post("/weekly-dispatch/{dispatch_id}/schedule", response_model=WeeklyDispatchDetail)
async def schedule_weekly_dispatch(
    dispatch_id: int, _admin: AdminDep, db: DbDep,
) -> WeeklyDispatchDetail:
    """★「计划发送」(主)· uploaded/scheduled→scheduled · 纯标记不发 · 等周日21:00 · 已sent→409。"""
    try:
        rec = await wd_service.schedule_dispatch(db, dispatch_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="周报投递不存在")
    return _weekly_detail(rec)


@router.post(
    "/weekly-dispatch/{dispatch_id}/cancel-schedule", response_model=WeeklyDispatchDetail,
)
async def cancel_weekly_dispatch_schedule(
    dispatch_id: int, _admin: AdminDep, db: DbDep,
) -> WeeklyDispatchDetail:
    """「取消计划」· scheduled → uploaded(21:00前撤回改稿)· 非 scheduled → 409 · 不存在 404。"""
    try:
        rec = await wd_service.cancel_schedule(db, dispatch_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="周报投递不存在")
    return _weekly_detail(rec)


@router.post("/weekly-dispatch/{dispatch_id}/send-now", response_model=WeeklySendOut)
async def send_weekly_dispatch_now(
    dispatch_id: int, _admin: AdminDep, db: DbDep,
) -> WeeklySendOut:
    """★「立即发送」(辅)· 当场发送 · 已发幂等跳过 · 不存在 404 · OSS 下载失败 502。"""
    rec = await wd_service.get_dispatch(db, dispatch_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="周报投递不存在")
    try:
        result = await wd_service.dispatch_and_send(db, year=rec.year, week=rec.week)
    except ObjectStoreError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"PDF 下载失败:{e}",
        ) from e
    return WeeklySendOut(
        dispatch_id=result.dispatch_id, year=result.year, week=result.week,
        recipients=result.recipients, email_sent=result.email_sent,
        email_failed=result.email_failed, notify_sent=result.notify_sent,
        notify_failed=result.notify_failed, skipped=result.skipped,
    )


# ── X 营销每日推文(阶段4a · PR-2)· admin 触发生成(异步)──────────────────────


class XTweetGenerateOut(BaseModel):
    """触发生成响应。"""

    status: str = Field(description="enqueued = 已入队 · worker 异步生成")
    message: str


@router.post(
    "/x-tweets/generate",
    summary="触发生成今日推文(异步 · 选币→DeepSeek→门禁→存待发 · 不发 X)",
)
async def generate_x_tweets(admin: AdminDep) -> XTweetGenerateOut:
    """admin 点「生成今日推文」· enqueue worker 异步生成(DeepSeek 慢,不阻塞 HTTP)。

    生成结果存 x_tweet(status=draft 待发 · ★门禁不过也存,后台可见但 4b 不发)· 本端点零 X 调用。
    """
    enqueue_daily_generation(admin.id)
    return XTweetGenerateOut(
        status="enqueued", message="已触发生成 · 约数十秒后在列表查看(异步)",
    )


class XTweetDispatchItem(BaseModel):
    """单条推文在某平台的发布状态(发布层 PR-3 · 前端按平台显状态/链接)。"""

    platform: str
    status: str  # pending / success / failed
    url: str | None  # 成功后的帖子链接
    error: str | None  # 失败原因(含平台错误码)
    source: str = "manual"  # 发布来源 · manual 人工 / auto 自动托管(PR-1 审计)


class XTweetItem(BaseModel):
    """单条推文(后台展示 · 72h 临时)。"""

    id: int
    symbol: str
    bias: str
    tweet_text: str
    compliance_passed: bool
    compliance_reason: str | None
    status: str  # draft 待发(4b 才会有 sent 等)
    image_path: str | None  # PR-4 截图后非空 · 现阶段 null
    created_at: datetime
    auto_drafted: bool = False  # ★自动托管起草(待补发素材标识 · 频率调整)
    has_url: bool = False  # ★正文含 URL(发 X 贵十几倍 · 前端提醒成本 · 非门禁否决)
    dispatches: list[XTweetDispatchItem] = []  # 各平台发布状态(发布层 PR-3)


class XTweetListOut(BaseModel):
    items: list[XTweetItem]
    total: int


def _to_dispatch_item(d: PlatformDispatch) -> XTweetDispatchItem:
    return XTweetDispatchItem(
        platform=d.platform, status=d.status, url=d.platform_post_url, error=d.error,
        source=d.source,
    )


def _to_tweet_item(
    row: XTweet, dispatches: list[PlatformDispatch] | None = None,
) -> XTweetItem:
    return XTweetItem(
        id=row.id, symbol=row.symbol, bias=row.bias, tweet_text=row.tweet_text,
        compliance_passed=row.compliance_passed, compliance_reason=row.compliance_reason,
        status=row.status, image_path=row.image_path, created_at=row.created_at,
        auto_drafted=row.auto_drafted,
        has_url=has_body_url(row.tweet_text),
        dispatches=[_to_dispatch_item(d) for d in (dispatches or [])],
    )


@router.get("/x-tweets", summary="今日推文列表(72h · 含门禁结果 + 各平台发布状态)")
async def list_x_tweets(_admin: AdminDep, db: DbDep) -> XTweetListOut:
    """最近 72h 生成的推文(created_at desc)· ★门禁不过的也列出 · 带各平台发布状态。"""
    rows = await list_recent(db)
    # ★批量查 dispatches(一次)避 N+1 · 按 tweet_id 分组
    by_tweet: dict[int, list[PlatformDispatch]] = {}
    for d in await list_dispatches_for_tweets(db, [r.id for r in rows]):
        by_tweet.setdefault(d.tweet_id, []).append(d)
    items = [_to_tweet_item(r, by_tweet.get(r.id)) for r in rows]
    return XTweetListOut(items=items, total=len(items))


@router.get("/x-tweets/{tweet_id}", summary="单条推文详情(含各平台发布状态)")
async def get_x_tweet(tweet_id: int, _admin: AdminDep, db: DbDep) -> XTweetItem:
    """单条推文详情 · 不存在 404(可能已过 72h 被清理)。"""
    row = await get_tweet(db, tweet_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推文不存在或已过期")
    return _to_tweet_item(row, await list_dispatches(db, tweet_id))


@router.get("/x-tweets/{tweet_id}/image", summary="推文 K线主图截图(x-shooter 截 · 共享卷读)")
async def get_x_tweet_image(tweet_id: int, _admin: AdminDep, db: DbDep) -> FileResponse:
    """读共享卷的截图 PNG(FileResponse)· 无截图 / 文件不存在(未截好或已过 24h)→ 404。"""
    row = await get_tweet(db, tweet_id)
    if row is None or not row.image_path or not Path(row.image_path).is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="截图不存在")
    return FileResponse(
        row.image_path, media_type="image/png",
        headers={"Cache-Control": "private, max-age=600"},
    )


# ── X 营销发布层(发布层 PR-1)· admin 显式发布到平台 ─────────────────────────


class PublishIn(BaseModel):
    """发布请求体。"""

    platform: str = Field(description="平台标识 · binance_square / x(目前仅 binance_square 可发)")


class PublishOut(BaseModel):
    dispatch_id: int
    platform: str
    status: str
    message: str


@router.post(
    "/x-tweets/{tweet_id}/publish",
    summary="发布推文到平台(★admin 单次显式触发 · 只发门禁通过 · 幂等防重 · 频率守卫)",
)
async def publish_x_tweet(
    tweet_id: int, payload: PublishIn, admin: AdminDep, db: DbDep,
) -> PublishOut:
    """★红线:发布永远 admin 显式单次点击(无自动/定时/批量)· 异步 enqueue worker 发。

    硬校验(任一不过即拒,绝不发):① 平台 adapter 存在且就绪 ② 门禁通过 ③ 未重复发 ④ 频率没超。
    """
    adapter = get_adapter(payload.platform)
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持或暂未接入的平台:{payload.platform}",
        )
    if not adapter.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{payload.platform} 未配置 API Key,无法发布",
        )
    tweet = await get_tweet(db, tweet_id)
    if tweet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推文不存在或已过期")
    if not tweet.compliance_passed:  # ★只发门禁通过的(防 F12 绕过)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="该推文门禁未通过,不可发布",
        )
    existing = await get_dispatch(db, tweet_id, payload.platform)
    if existing is not None and existing.status == "success":  # ★幂等防重复发
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"已发布到 {payload.platform},不重复发",
        )
    redis = await get_redis()  # ★频率守卫(防风控)
    ok, reason = await check_rate(redis, payload.platform)
    if not ok:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=reason)
    # ★自动托管素材(auto_drafted)的人工补发也计入 30 日配额(配额"算":自动发+补发 ≤30 · 封号总量可控)
    if tweet.auto_drafted and await auto_guard.daily_remaining(redis) <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="今日自动托管配额(30 条)已满,明日再补发此素材",
        )

    dispatch = await upsert_pending(
        db, tweet_id=tweet_id, platform=payload.platform, dispatched_by=admin.id,
        source="manual",  # ★后台人工点 = manual(自动托管走 auto · PR-2/3)
    )
    enqueue_publish(dispatch.id)  # ★异步发布(真 API 慢 · worker 跑)
    return PublishOut(
        dispatch_id=dispatch.id, platform=payload.platform, status="pending",
        message="已提交发布 · 稍后查看状态",
    )


# ── X 营销自动托管(自动托管 PR-1)· 全局开关 + 紧急熔断 ─────────────────────


class AutoPilotStatus(BaseModel):
    enabled: bool          # 自动托管总开关(默认 OFF)
    circuit_open: bool     # 熔断中(连续失败触发 · 开则停所有自动发)
    daily_used: int        # 今日已自动发布数
    daily_remaining: int   # 今日剩余配额(30 封顶)
    in_window: bool        # 当前是否在发布时段(7:30-22:30 CST)


class AutoPilotToggleIn(BaseModel):
    enabled: bool


@router.get("/x-auto/status", summary="自动托管状态(开关/熔断/日配额/时段)")
async def get_auto_pilot_status(_admin: AdminDep) -> AutoPilotStatus:
    redis = await get_redis()
    remaining = await auto_guard.daily_remaining(redis)
    return AutoPilotStatus(
        enabled=await auto_guard.is_enabled(redis),
        circuit_open=await auto_guard.is_circuit_open(redis),
        daily_used=auto_guard.AUTO_DAILY_MAX - remaining,
        daily_remaining=remaining,
        in_window=auto_guard.is_in_publish_window(),
    )


@router.post("/x-auto/toggle", summary="开/关自动托管(★默认 OFF · 开=自动起草+自动发)")
async def toggle_auto_pilot(payload: AutoPilotToggleIn, _admin: AdminDep) -> AutoPilotStatus:
    """★全自动托管总开关 · 开则 worker beat 自动起草+发布(门禁/频率/时段/熔断守卫照常)。"""
    redis = await get_redis()
    await auto_guard.set_enabled(redis, payload.enabled)
    if payload.enabled:  # 重新开启 → 清熔断(给个干净起点)
        await auto_guard.close_circuit(redis)
    logger.info("[x-auto] 自动托管开关 → %s", payload.enabled)
    return await get_auto_pilot_status(_admin)


class AutoPilotStopOut(BaseModel):
    stopped: bool
    revoked: int  # revoke 掉的排队中自动发布任务数
    message: str


@router.post("/x-auto/stop", summary="★紧急熔断:立刻停止自动托管(关开关 + 熔断 + revoke 排队任务)")
async def stop_auto_pilot(_admin: AdminDep) -> AutoPilotStopOut:
    """★紧急刹车 · 关总开关 + 开熔断 + revoke 排队中的 auto-publish 任务(三重停)。"""
    redis = await get_redis()
    await auto_guard.set_enabled(redis, enabled=False)
    await auto_guard.open_circuit(redis)
    revoked = revoke_auto_tasks(await auto_guard.pop_pending_tasks(redis))
    logger.warning("[x-auto] ★紧急熔断触发 · revoke %d 个排队任务", revoked)
    return AutoPilotStopOut(
        stopped=True, revoked=revoked,
        message=f"已停止自动托管 · 关开关 + 熔断 + revoke {revoked} 个排队任务",
    )
# ★托管交易(策略前向测试)admin 端点在独立模块 api/v1/managed_admin.py —— ★admin 域不得 import
#   virtual_trading(架构守卫 test_admin_domain_no_engine_no_login_import 递归扫 admin import 树)。
