"""增长机制 · 试用 + 邀请(Phase 1.5 刀A)。

Hans 拍板:试用 verify 时发(Google create 即时)· 邀请双向各 15 天 ·
累积封顶 90 天(invite 受限 · trial 不受限)· 防刷底线 = 受邀方邮箱验证后兑现 ·
存量用户不追溯(verify/create 都是新用户路径,天然成立)。

🔴 纪律:归因/兑现/试用全部 try/except 包死 —— 增长逻辑任何异常绝不阻塞
注册/验证/登录主链路(失败仅 warning,用户无感)。
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation
from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)

TRIAL_DAYS = 7
INVITE_DAYS = 15
INVITE_CAP_DAYS = 90  # invite 来源累积封顶(now + 90d)· trial 不受限

# Crockford base32(去易混 I/L/O/U)· 8 位 ≈ 1.1e12 空间,撞码由 unique 约束兜底重试
_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_LEN = 8


def _gen_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))


# ── 订阅延长(三态 + 封顶)──────────────────────────────────────────────────


async def extend_subscription(
    db: AsyncSession,
    user_id: UUID,
    days: int,
    source: str,
    *,
    cap_days: int | None = None,
) -> datetime | None:
    """延长(或开通)pro 订阅 · 返回新 expires_at;封顶已满无增量 → None。

    三态:无行 INSERT(now+days)/ 有效行累加(expires+days)/
    过期或非 active 从 now 起算(过期部分不补)。
    cap_days:累加后不得超过 now+cap(invite=90 · trial 不传不受限)。
    并发:同行两次 UPDATE 在 PG 行锁下串行,累加不丢失(G3 确认)。
    """
    now = datetime.now(UTC)
    sub = await db.scalar(select(Subscription).where(Subscription.user_id == user_id))

    if sub is None:
        new_exp = now + timedelta(days=days)
        db.add(Subscription(
            user_id=user_id, plan="pro", status="active",
            started_at=now, expires_at=new_exp, source=source,
        ))
        await db.flush()
        return new_exp

    # 有效行累加 · 过期/非 active 从 now 起算
    active = sub.status == "active" and (sub.expires_at is None or sub.expires_at > now)
    base = sub.expires_at if (active and sub.expires_at is not None) else now
    new_exp = base + timedelta(days=days)
    if cap_days is not None:
        cap = now + timedelta(days=cap_days)
        new_exp = min(new_exp, cap)
        # 已达封顶 · 增量不足 1 小时视为零增量(容差盖住"再次调用时 cap 随 now
        # 前移几毫秒"的时钟抖动)→ None,调用方不展示"获赠"
        if new_exp - base < timedelta(hours=1):
            return None
    sub.plan = "pro"
    sub.status = "active"
    sub.expires_at = new_exp
    sub.source = source
    await db.flush()
    return new_exp


# ── 试用(每用户一次)────────────────────────────────────────────────────────


async def grant_trial_if_eligible(db: AsyncSession, user_id: UUID) -> bool:
    """新用户 7 天 pro 试用 · 只发一次。

    只发一次判定 = 「subscription 无行才发」(最简可靠):trial 是用户首个
    订阅事件,行一旦存在(trial 或 invite 先到)即不再发;verify 二次触发
    不可能(token 一次性),Google create 仅新建分支触发。
    ★ 顺序契约:verify/create 流程里 trial 必须先于邀请兑现调用,
      否则 invite 先开行会让 trial 误判「已有行」少发 7 天(单测钉死)。
    """
    try:
        existing = await db.scalar(
            select(Subscription.id).where(Subscription.user_id == user_id),
        )
        if existing is not None:
            return False
        await extend_subscription(db, user_id, TRIAL_DAYS, "trial")
        logger.info("[growth.trial] granted user=%s days=%d", user_id, TRIAL_DAYS)
        return True
    except Exception as e:  # noqa: BLE001 — 增长逻辑绝不阻塞主链路
        logger.warning("[growth.trial] failed user=%s err=%s", user_id, e)
        return False


# ── 邀请:归因(注册时)+ 兑现(验证后)──────────────────────────────────────


async def attribute_invite(db: AsyncSession, invitee_id: UUID, ref: str | None) -> None:
    """注册带 ?ref= → 写 invitation(pending)· 无效码/任何异常静默(绝不阻注册)。"""
    if not ref:
        return
    try:
        code = ref.strip().upper()
        if not code or len(code) > 12:
            return
        inviter = await db.scalar(select(User).where(User.invite_code == code))
        if inviter is None or inviter.id == invitee_id:
            return  # 无效码 / 自指(理论不可能 · 双保险)→ 静默
        db.add(Invitation(inviter_id=inviter.id, invitee_id=invitee_id, code=code))
        await db.flush()
        logger.info("[growth.invite] attributed inviter=%s invitee=%s", inviter.id, invitee_id)
    except Exception as e:  # noqa: BLE001 — 归因失败静默(invitee_id unique 冲突等)
        logger.warning("[growth.invite] attribute failed invitee=%s err=%s", invitee_id, e)


async def redeem_invite_if_pending(db: AsyncSession, invitee_id: UUID) -> bool:
    """受邀方邮箱验证后兑现:双向各 +15d(封顶 90d)· rowcount 幂等。

    UPDATE ... WHERE rewarded_at IS NULL:并发双验证恰好一次成功(G3 确认)。
    """
    try:
        result = await db.execute(
            update(Invitation)
            .where(Invitation.invitee_id == invitee_id, Invitation.rewarded_at.is_(None))
            .values(rewarded_at=datetime.now(UTC))
            .returning(Invitation.inviter_id),
        )
        row = result.first()
        if row is None:
            return False  # 无 pending(未被邀 / 已兑现)
        inviter_id = row[0]
        await extend_subscription(
            db, invitee_id, INVITE_DAYS, "invite", cap_days=INVITE_CAP_DAYS,
        )
        await extend_subscription(
            db, inviter_id, INVITE_DAYS, "invite", cap_days=INVITE_CAP_DAYS,
        )
        logger.info(
            "[growth.invite] redeemed inviter=%s invitee=%s +%dd",
            inviter_id, invitee_id, INVITE_DAYS,
        )
        return True
    except Exception as e:  # noqa: BLE001 — 兑现失败不阻塞验证主链路
        logger.warning("[growth.invite] redeem failed invitee=%s err=%s", invitee_id, e)
        return False


# ── 邀请码(lazy 生成)+ 统计 ────────────────────────────────────────────────


async def get_or_create_invite_code(db: AsyncSession, user: User) -> str:
    """首次访问邀请页生成(存量用户零回填)· 撞码(unique 冲突)重试 3 次。"""
    if user.invite_code is not None:
        return user.invite_code
    for _ in range(3):
        code = _gen_code()
        dup = await db.scalar(select(User.id).where(User.invite_code == code))
        if dup is None:
            user.invite_code = code
            await db.flush()
            return code
    raise RuntimeError("invite code 生成 3 次均撞码(1.1e12 空间 · 概率近零)")


async def invite_stats(db: AsyncSession, inviter_id: UUID) -> tuple[int, int]:
    """(已邀人数, 已兑现数)。"""
    invited = await db.scalar(
        select(func.count()).select_from(Invitation).where(
            Invitation.inviter_id == inviter_id,
        ),
    )
    rewarded = await db.scalar(
        select(func.count()).select_from(Invitation).where(
            Invitation.inviter_id == inviter_id, Invitation.rewarded_at.is_not(None),
        ),
    )
    return int(invited or 0), int(rewarded or 0)
