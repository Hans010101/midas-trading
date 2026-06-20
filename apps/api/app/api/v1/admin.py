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

from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.admin_action_log import AdminActionLog
from app.models.daily_visit_stat import DailyVisitStat
from app.models.redeem_code import RedeemCode
from app.models.session import Session
from app.models.subscription import Subscription
from app.models.user import User
from app.services.academy.admin_stats import get_academy_stats
from app.services.growth import extend_subscription, invite_stats
from app.services.membership import PLAN_QUOTAS, get_quota_used, resolve_plan
from app.services.visit_stats import CN_TZ, cn_today, read_redis_day

router = APIRouter(prefix="/admin", tags=["admin"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


class AdminUserItem(BaseModel):
    id: str
    email: str
    role: str
    banned: bool  # 刀3b-2:已停用
    plan: str  # 会员刀2:free / pro(subscription outerjoin 批量解析 · 防 N+1)
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

    def _plan_of(plan: str | None, sub_status: str | None, expires_at: datetime | None) -> str:
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
                plan=_plan_of(plan, sub_status, expires_at),
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


# ── 网站访问看板(PV/UV 趋势 + 注册趋势)· AdminDep · 纯只读 ──────────────────────
# 访问数据自上线起累积、历史不可回溯(部署前无访问日志);注册数据可回溯(user.created_at)。
# PV/UV:PG daily_visit_stat 历史 + Redis 今/昨实时叠加(不等下次 flush)。隐私:仅匿名计数。


class VisitDailyPoint(BaseModel):
    date: str  # ISO yyyy-mm-dd(CN 日)
    pv: int
    uv: int


class RegistrationPoint(BaseModel):
    date: str
    count: int


class VisitStatsOut(BaseModel):
    range_days: int
    daily: list[VisitDailyPoint]  # 近 N 天 PV/UV(含今日实时)
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

    return VisitStatsOut(
        range_days=days,
        daily=daily,
        registrations=registrations,
        today=today_pt,
        yesterday=yest_pt,
        cumulative_pv=cumulative_pv,
        cumulative_uv=cumulative_uv,
        total_registrations=int(total_reg),
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
