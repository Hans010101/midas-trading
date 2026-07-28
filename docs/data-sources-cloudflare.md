# Midas Trading · Cloudflare 数据源矩阵

更新日期：2026-07-28

本项目只读参考旧 `midas` 的数据字段、周期、时区和降级经验，不调用旧项目 API，
也不写入旧项目数据库。数据采集与缓存全部运行在 Midas Trading 自己的 Cloudflare
Worker 和 D1 中。

| 数据域 | 主源 | 备用/降级 | 缓存与说明 |
| --- | --- | --- | --- |
| 加密现货 K 线 | OKX 公共现货蜡烛图 | Kraken 公共现货 OHLC | 无需 API Key；返回真实 source 和 data_as_of |
| 加密永续 K 线 | OKX 公共 USDT Swap 蜡烛图 | Kraken Futures 公共 Trade Candles | 覆盖 AGLD 等 Kraken Spot 不支持的标的 |
| 加密永续行情与衍生指标 | Kraken Futures tickers / analytics | 字段不可得时明确返回 unavailable_fields | 不伪造多空比、资金费率或持仓量 |
| 加密全市场总览 | CoinGecko `/global` | 单源失败时保留其他来源 | 总市值、24h 成交额、BTC/ETH 市占率 |
| 恐慌贪婪指数 | Alternative.me FGI | 失败时标记不可用 | 不再使用固定 0 占位 |
| 美股 K 线 | Yahoo Finance query1 chart | Yahoo Finance query2 chart | 支持分钟、小时、日、周周期 |
| A 股 K 线 | Yahoo Finance 沪深映射 | Yahoo Finance query2 | Worker 侧避免引入仅适合常驻 Python 的 AKShare |
| 港股 K 线 | Yahoo Finance `.HK` 映射 | Yahoo Finance query2 | 统一五位港股代码 |
| 三地市场首页 | Yahoo 报价采集 | D1 最近成功快照 | 每 10 分钟轮换刷新，单次失败不清空旧快照 |
| 全球指数/商品/外汇/债券 | Yahoo chart | D1 最近成功快照 | 与三地行情错峰刷新 |
| 财经日历 | Federal Reserve + BEA 官方 JSON | 可验证规则与明确标记的 seed | 返回逐源 stale 状态，不把推算日期冒充官方确认 |
| 标的搜索 | Yahoo Search（股票）/ OKX Instruments（加密） | 本地核心标的种子 | 支持搜索新增币种和股票，不再局限于硬编码清单 |

## 运行规则

- 上游超时上限 8–12 秒；主源异常自动进入备用源。
- API 返回 `source`、`fallback_used`、`data_as_of`，便于前端和运维判断数据质量。
- D1 只保存独立项目的市场首页与全球概览快照。
- `/api/v1/market/data-sources/health` 同时探测股票、AGLD 永续 K 线及 D1
  三地市场/全球概览快照。
- GitHub Actions 发布后必须验证 AGLD K 线、加密总市值、三地市场首页及数据源健康状态。
