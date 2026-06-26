"""x-shooter 截图(阶段4a · PR-4)· 复用阶段1 POC 验证逻辑。

开公开 crypto-preview?symbol=X → 等 K线渲染(networkidle + 主图卡可见 + 延时兜底)→
截【主图卡区域】(K线+布林+MACD+缠论 · 不含下方 AI 策略/AI 决策卡)→ 存 /shots/<id>.png。

★ 串行(concurrency=1)· 每次 launch→close 释放(1.5g 内不堆浏览器)· root 容器须 --no-sandbox。
★ 中文靠镜像装的 fonts-noto-cjk(阶段1 头号坑)。
★ best-effort:任何失败返回 error dict(永不 raise · 不阻塞主 worker 链路 · 单条失败不影响其他)。
★ 截公开页(不需 Pro 登录 · 阶段1 验证)。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# 公开 crypto-preview(阶段1 验证渲染正常)· 可经 env 覆盖(内网 web:3000 等)。
_BASE_URL = os.environ.get("XSHOT_BASE_URL", "https://midastrade.asia")
_SHOTS_DIR = os.environ.get("XSHOT_DIR", "/shots")
# 主图卡:含「主图:K 线 + 布林带 + MACD + 缠论」标题的卡片(crypto-main-chart.tsx)·
# K线/布林/MACD/缠论 全在此卡内,AI 策略/决策卡是页面下方独立兄弟节点 → 天然排除。
_CARD_SELECTOR = "div.bg-surface-card"
_CARD_TEXT = "主图:K 线 + 布林带 + MACD + 缠论"


def capture_one(tweet_id: int, symbol: str) -> dict:
    """截一条推文的主图卡 → /shots/<tweet_id>.png · 返回 {tweet_id,status,path?/error?}。"""
    out_path = str(Path(_SHOTS_DIR) / f"{tweet_id}.png")
    url = f"{_BASE_URL}/crypto-preview?symbol={symbol}"
    try:
        with sync_playwright() as pw:
            # root 容器 Chromium 必须 --no-sandbox · disable-dev-shm 防 /dev/shm 太小崩。
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page(
                    viewport={"width": 1280, "height": 1100}, device_scale_factor=2,
                )
                # ① networkidle:等数据请求基本静默(K线/指标拉完)
                page.goto(url, wait_until="networkidle", timeout=60000)
                # ② 主图卡可见
                card = page.locator(_CARD_SELECTOR).filter(has_text=_CARD_TEXT).first
                card.wait_for(state="visible", timeout=30000)
                # ③ 延时兜底:K线 canvas 完成绘制(networkidle 不保证 canvas 画完)
                page.wait_for_timeout(2500)
                card.screenshot(path=out_path)
            finally:
                browser.close()  # ★ 截完即释放(串行 · 不堆浏览器)
        Path(out_path).chmod(0o644)  # 共享卷可读(root 写 · api/worker 读删)
        logger.info("[xshot] captured tweet=%s symbol=%s → %s", tweet_id, symbol, out_path)
        return {"tweet_id": tweet_id, "status": "ok", "path": out_path}
    except Exception as exc:  # noqa: BLE001 · ★best-effort:失败不 raise,不阻塞主链路
        logger.warning("[xshot] FAILED tweet=%s symbol=%s · %s", tweet_id, symbol, exc)
        return {"tweet_id": tweet_id, "status": "error", "error": str(exc)}
