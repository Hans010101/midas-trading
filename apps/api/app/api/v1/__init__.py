from fastapi import APIRouter

from app.api.v1.academy import router as academy_router
from app.api.v1.admin import router as admin_router
from app.api.v1.alert_rules import router as alert_rules_router
from app.api.v1.analysis import router as analysis_router
from app.api.v1.auth import router as auth_router
from app.api.v1.backtest import router as backtest_router
from app.api.v1.bot_preset import router as bot_preset_router
from app.api.v1.chart import router as chart_router
from app.api.v1.cn import router as cn_router
from app.api.v1.crypto import router as crypto_router
from app.api.v1.feishu import router as feishu_router
from app.api.v1.hk import router as hk_router
from app.api.v1.invite import router as invite_router
from app.api.v1.market import router as market_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.overview import router as overview_router
from app.api.v1.payment import router as payment_router
from app.api.v1.perp import router as perp_router
from app.api.v1.quota import router as quota_router
from app.api.v1.redeem import router as redeem_router
from app.api.v1.structure import router as structure_router
from app.api.v1.support import router as support_router
from app.api.v1.telegram import router as telegram_router
from app.api.v1.track import router as track_router
from app.api.v1.us import router as us_router
from app.api.v1.user import router as user_router
from app.api.v1.virtual import router as virtual_router
from app.api.v1.watchlist import router as watchlist_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(market_router)
router.include_router(watchlist_router)
router.include_router(virtual_router)
router.include_router(perp_router)
router.include_router(notifications_router)
router.include_router(telegram_router)
# ADR 0032 阶段二 · 飞书事件回调(URL 握手 + 验签 + 收事件)
router.include_router(feishu_router)
router.include_router(analysis_router)
router.include_router(alert_rules_router)
router.include_router(bot_preset_router)
# KLINE-001 · K线图 PNG 端点(bot sendPhoto · 只读渲染)
router.include_router(chart_router)
router.include_router(crypto_router)
# 0023 阶段③ · A股/美股 市场首页(3.1 基建:状态 + 大盘指数)
router.include_router(cn_router)
router.include_router(us_router)
# 港股首页全市场 · 状态 + 大盘指数(恒生/国企)+ 全市场榜单 + 涨跌家数(新浪源)
router.include_router(hk_router)
# ADR 0035 阶段 A · 全球指标概览(只读 · 不涉及交易)
router.include_router(overview_router)
# P1-4c.5(ADR 0038)· 研究室回测 full-data 读端点(只读 · authed-only 按 user 过滤 · 不涉及交易)
router.include_router(backtest_router)
# 结构分析助手第1刀 · 7 因子结构快照(只读 CH · authed · 非预测不交易)
router.include_router(structure_router)
# 用户管理刀1 · 管理员用户列表(AdminDep 403 唯一边界 · 纯只读)
router.include_router(admin_router)
# 会员 Phase 1 刀1 · AI 额度自报(authed · 前端展示共用)
router.include_router(quota_router)
# Phase 1.5 刀A · 邀请有礼(lazy 码 + 统计)
router.include_router(invite_router)
# 兑换码模块刀1 · 管理员生成/列表 + 用户兑换(开 pro 权益 · source='redeem')
router.include_router(redeem_router)
# Phase 2a 刀1 · 会员订阅支付(Bcon USDT/BSC · 建单 + 回调核验开 pro · source='paid')
# 🔴 红线:支付域不碰 engine(收订阅费非交易)· 凭证只从 env 读
router.include_router(payment_router)
# 支付工单 / 退款申请(support 模块 · authed)· 工单存 DB + Resend 通知客服 · 图走附件不落盘
# 🔴 红线:独立模块不碰 engine/收款逻辑 · 身份从 session 取 · Resend key env 读不入日志
router.include_router(support_router)
# 用户资料(头像选择器骨架)· PATCH /user/avatar 零图片存储只存编号
router.include_router(user_router)
# 访问看板埋点 ingest · Next 中间件 beacon 调用 · 公开端点只 bump Redis 计数(不写 PG · 仅匿名 vid)
router.include_router(track_router)
# 训练营 B 期刀1 · 学习进度追踪(标记学完 + 进度展示)· 纯增量只读写 academy_progress
# 🔴 红线:不碰交易/支付/会员 · article_slug 用 catalog 校验 · 未登录 GET 返空进度不 401
router.include_router(academy_router)
