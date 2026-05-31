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
    # 精选扩充 +10(都 yfinance 实测可采 · 零迁移)· 有独立地理的上地图,其余进卡片
    ("^NSEI", "印度NIFTY", "in", "index", "point"),
    ("^TWII", "台湾加权", "tw", "index", "point"),
    ("^BVSP", "巴西BOVESPA", "br", "index", "point"),
    ("^GSPTSE", "加拿大TSX", "ca", "index", "point"),
    ("^SSMI", "瑞士SMI", "ch", "index", "point"),
    ("^JKSE", "印尼综合", "id", "index", "point"),
    ("^STOXX50E", "欧洲STOXX50", "eu", "index", "point"),
    ("^RUT", "罗素2000", "us", "index", "point"),
    ("000300.SS", "沪深300", "cn", "index", "point"),
    ("399001.SZ", "深证成指", "cn", "index", "point"),
    # ── 商品期货(13)─────────────────────────────
    ("GC=F", "黄金", "global", "commodity", "price"),
    ("SI=F", "白银", "global", "commodity", "price"),
    ("CL=F", "WTI原油", "global", "commodity", "price"),
    ("BZ=F", "布伦特原油", "global", "commodity", "price"),
    ("HG=F", "铜", "global", "commodity", "price"),
    ("NG=F", "天然气", "global", "commodity", "price"),
    ("PL=F", "铂金", "global", "commodity", "price"),
    ("PA=F", "钯金", "global", "commodity", "price"),
    ("ZS=F", "大豆", "global", "commodity", "price"),
    ("ZC=F", "玉米", "global", "commodity", "price"),
    ("ZW=F", "小麦", "global", "commodity", "price"),
    ("KC=F", "咖啡", "global", "commodity", "price"),
    ("SB=F", "糖", "global", "commodity", "price"),
    # ── 外汇(9)──────────────────────────────────
    ("DX-Y.NYB", "美元指数", "fx", "forex", "rate"),
    ("JPY=X", "美元日元", "fx", "forex", "rate"),
    ("EURUSD=X", "欧元美元", "fx", "forex", "rate"),
    ("CNY=X", "美元人民币", "fx", "forex", "rate"),
    ("GBPUSD=X", "英镑美元", "fx", "forex", "rate"),
    ("AUDUSD=X", "澳元美元", "fx", "forex", "rate"),
    ("USDCAD=X", "美元加元", "fx", "forex", "rate"),
    ("USDHKD=X", "美元港币", "fx", "forex", "rate"),
    ("USDKRW=X", "美元韩元", "fx", "forex", "rate"),
    # ── 债券收益率(4)· yield_pct · 涨跌 bp ─────────
    ("^TNX", "美债10年", "us", "bond", "yield_pct"),
    ("^TYX", "美债30年", "us", "bond", "yield_pct"),
    ("^FVX", "美债5年", "us", "bond", "yield_pct"),
    ("2YY=F", "美债2年", "us", "bond", "yield_pct"),
    # ── 市场情绪 / 波动率(4)· 无地理 → 仅卡片 · VIX 涨=避险升,颜色仍按数值红涨绿跌 ──
    ("^VIX", "VIX恐慌指数", "global", "sentiment", "point"),
    ("^VXN", "纳指VIX", "global", "sentiment", "point"),
    ("^OVX", "原油波动率", "global", "sentiment", "point"),
    ("^MOVE", "美债波动率MOVE", "global", "sentiment", "point"),
)

# 加密(复用 crypto_ticker_24h · ccxt 已采)· (ccxt symbol, 中文名)
# ★ 读 perp 行情(bulk 全市场常采、稳定);spot 采集未常态化、数据会过期 → 见 clickhouse_overview.py。
CRYPTO_OVERVIEW: tuple[tuple[str, str], ...] = (
    ("BTC/USDT", "比特币"),
    ("ETH/USDT", "以太坊"),
    ("SOL/USDT", "Solana"),
    ("BNB/USDT", "BNB"),
    ("XRP/USDT", "瑞波XRP"),
    ("TRX/USDT", "波场TRX"),
    ("DOGE/USDT", "狗狗币"),
)

# 分类展示标签 + 顺序
CATEGORY_LABELS: dict[str, str] = {
    "index": "环球指数",
    "commodity": "商品期货",
    "forex": "外汇",
    "bond": "债券收益率",
    "sentiment": "市场情绪",
    "crypto": "加密货币",
}
CATEGORY_ORDER: tuple[str, ...] = ("index", "commodity", "forex", "bond", "sentiment", "crypto")

# symbol → 展示顺序(API 分组内按此重排 · 缺数据的略过不影响顺序)
_ALL_SYMBOLS: tuple[str, ...] = (
    *(s for s, *_ in GLOBAL_OVERVIEW_YF),
    *(s for s, _ in CRYPTO_OVERVIEW),
)
OVERVIEW_SYMBOL_ORDER: dict[str, int] = {sym: i for i, sym in enumerate(_ALL_SYMBOLS)}
CRYPTO_NAME: dict[str, str] = dict(CRYPTO_OVERVIEW)
