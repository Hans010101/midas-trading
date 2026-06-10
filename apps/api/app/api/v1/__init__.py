from fastapi import APIRouter

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
from app.api.v1.market import router as market_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.overview import router as overview_router
from app.api.v1.perp import router as perp_router
from app.api.v1.structure import router as structure_router
from app.api.v1.telegram import router as telegram_router
from app.api.v1.us import router as us_router
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
