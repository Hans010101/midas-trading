"""A股 / 美股 市场首页配置常量(0023 阶段③ · 3.1)。

集中放「采哪些指数 / 展示顺序 / 展示名」· 采集任务、CH 读取、API 路由共用,
避免散落各处。
"""

from __future__ import annotations

# A股大盘指数(0023 §1)· Sina 代码(stock_zh_index_spot_sina 的「代码」列)· 展示顺序
# 名称直接取 Sina「名称」列(上证指数 / 深证成指 / 创业板指 / 沪深300)· 无需本地映射
CN_INDEX_CODES: tuple[str, ...] = ("sh000001", "sz399001", "sz399006", "sh000300")

# 美股大盘指数(0023 §2)· yfinance 代码 → 展示名(yfinance 不给中文名 · 本地映射)
US_INDICES: tuple[tuple[str, str], ...] = (
    ("^DJI", "道琼斯"),
    ("^IXIC", "纳斯达克"),
    ("^GSPC", "标普500"),
    ("^RUT", "罗素2000"),
)
US_INDEX_ORDER: tuple[str, ...] = tuple(sym for sym, _ in US_INDICES)
