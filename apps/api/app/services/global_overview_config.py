"""全球指标概览 · 采集 symbol 清单 + 分类(ADR 0035 阶段 A)。

★ 产品负责人 2026-05-30 拍板的首批清单(§1.3 收窄版:无指数期货 / 无天然气 / 无英镑)。
- yfinance 通用 ticker 采集(指数 / 商品 / 外汇 / 债券)→ `market_index_snapshot`(category 标记)。
- 加密复用现有 ccxt 采集的 `crypto_ticker_24h`(不用 yfinance 加密)→ 概览 API 读时合并。
- `market` 列存【地区码】(us/jp/hk/cn/de/uk/global/fx)· 同时是阶段 B 地图定位键。
- ★ 红线:全球指标只读展示,地区码不是交易 `Market`(cn/us/crypto/hk),不可交易、不建钱包。
"""

from __future__ import annotations

# (yfinance ticker, 中文名, 地区码, category, unit)
# unit:point 点位 / price 价格 / rate 汇率 / yield_pct 收益率%(涨跌用 bp)
GLOBAL_OVERVIEW_YF: tuple[tuple[str, str, str, str, str], ...] = (
    # ── 环球指数(12)─────────────────────────────
    ("^GSPC", "标普500", "us", "index", "point"),
    ("^IXIC", "纳斯达克", "us", "index", "point"),
    ("^DJI", "道琼斯", "us", "index", "point"),
    ("^N225", "日经225", "jp", "index", "point"),
    ("^HSI", "恒生指数", "hk", "index", "point"),
    ("000001.SS", "上证指数", "cn", "index", "point"),
    ("^GDAXI", "德国DAX", "de", "index", "point"),
    ("^FTSE", "英国富时100", "uk", "index", "point"),
    # 阶段B 迭代扩充(地图更饱满 · 都有明确地理归属 · 复用 yfinance · 零迁移)
    ("^KS11", "韩国KOSPI", "kr", "index", "point"),
    ("^STI", "新加坡STI", "sg", "index", "point"),
    ("^FCHI", "法国CAC40", "fr", "index", "point"),
    ("^AXJO", "澳洲ASX200", "au", "index", "point"),
    # ── 商品期货(5)──────────────────────────────
    ("GC=F", "黄金", "global", "commodity", "price"),
    ("SI=F", "白银", "global", "commodity", "price"),
    ("CL=F", "WTI原油", "global", "commodity", "price"),
    ("BZ=F", "布伦特原油", "global", "commodity", "price"),
    ("HG=F", "铜", "global", "commodity", "price"),
    # ── 外汇(4)──────────────────────────────────
    ("DX-Y.NYB", "美元指数", "fx", "forex", "rate"),
    ("JPY=X", "美元日元", "fx", "forex", "rate"),
    ("EURUSD=X", "欧元美元", "fx", "forex", "rate"),
    ("CNY=X", "美元人民币", "fx", "forex", "rate"),
    # ── 债券收益率(3)· yield_pct · 涨跌 bp ─────────
    ("^TNX", "美债10年", "us", "bond", "yield_pct"),
    ("^TYX", "美债30年", "us", "bond", "yield_pct"),
    ("^FVX", "美债5年", "us", "bond", "yield_pct"),
)

# 加密(复用 crypto_ticker_24h · ccxt 已采)· (ccxt symbol, 中文名)
CRYPTO_OVERVIEW: tuple[tuple[str, str], ...] = (
    ("BTC/USDT", "比特币"),
    ("ETH/USDT", "以太坊"),
)

# 分类展示标签 + 顺序(无指数期货 · 拍板版)
CATEGORY_LABELS: dict[str, str] = {
    "index": "环球指数",
    "commodity": "商品期货",
    "forex": "外汇",
    "bond": "债券收益率",
    "crypto": "加密货币",
}
CATEGORY_ORDER: tuple[str, ...] = ("index", "commodity", "forex", "bond", "crypto")

# symbol → 展示顺序(API 分组内按此重排 · 缺数据的略过不影响顺序)
_ALL_SYMBOLS: tuple[str, ...] = (
    *(s for s, *_ in GLOBAL_OVERVIEW_YF),
    *(s for s, _ in CRYPTO_OVERVIEW),
)
OVERVIEW_SYMBOL_ORDER: dict[str, int] = {sym: i for i, sym in enumerate(_ALL_SYMBOLS)}
CRYPTO_NAME: dict[str, str] = dict(CRYPTO_OVERVIEW)
