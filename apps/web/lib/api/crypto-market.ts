/**
 * 加密市场列表页 API client(M2-D · /crypto-market)。
 *
 * 独立于 lib/api/crypto.ts(详情页用)· 只服务列表页,避免动详情页代码。
 * 走 M2-A 已有的只读端点:
 *   GET /api/v1/crypto/overview          · 全市场总览(总市值/合约成交额/FGI)
 *   GET /api/v1/crypto/tickers/24h?...    · 24h ticker 榜单(分 spot/perp)
 *
 * 红线:接不上的字段交给页面显示「—」/ 空态,绝不在此伪造数据。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type Instrument = 'spot' | 'perp'

export interface Ticker24h {
  symbol: string // ccxt 风格 'BTC/USDT'
  instrument: Instrument
  ts: string
  last_price: number
  change_pct_24h: number // 已乘 100 · % 单位
  high_24h: number
  low_24h: number
  volume_24h: number
  quote_volume_24h: number // USDT 计成交额
  count_24h: number
}

export interface Tickers24hResponse {
  instrument: Instrument
  sort_by: string
  order: string
  items: Ticker24h[]
}

export interface MarketOverview {
  ts: string
  total_market_cap_usd: number
  total_volume_24h_usd: number
  btc_dominance: number
  eth_dominance: number
  fear_greed_value: number
  fear_greed_classification: string
  derivatives_oi_usd: number
  derivatives_volume_24h_usd: number
}

export interface CryptoOverviewResponse {
  market_overview: MarketOverview
  top_gainers: Ticker24h[]
  top_losers: Ticker24h[]
  top_volume: Ticker24h[]
  // BTC/ETH 价格卡专用 · 后端按 symbol 精确取(不在涨跌幅榜上也能拿到)· 无则 null
  btc_ticker: Ticker24h | null
  eth_ticker: Ticker24h | null
}

export class CryptoMarketApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`CryptoMarketApi ${status}: ${detail}`)
    this.name = 'CryptoMarketApiError'
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { signal })
  if (!r.ok) {
    let detail = `HTTP ${r.status}`
    try {
      const body = (await r.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* ignore */
    }
    throw new CryptoMarketApiError(r.status, detail)
  }
  return (await r.json()) as T
}

/** 24h ticker 榜单 · 默认按 24H 涨跌降序 · top 取够分页(M2-A 实际可能 < 100)。 */
export function fetchTickers24h(
  instrument: Instrument,
  top = 100,
  signal?: AbortSignal,
): Promise<Tickers24hResponse> {
  const params = new URLSearchParams({
    instrument,
    sort_by: 'change_pct_24h',
    order: 'desc',
    top: String(top),
  })
  return getJson<Tickers24hResponse>(`/api/v1/crypto/tickers/24h?${params.toString()}`, signal)
}

/** 全市场总览(总市值 / dominance / 合约成交额 / FGI)。 */
export function fetchCryptoOverview(signal?: AbortSignal): Promise<CryptoOverviewResponse> {
  return getJson<CryptoOverviewResponse>('/api/v1/crypto/overview', signal)
}

// ── 榜单级合约指标批量(任务3)· 列表页 3 列(资金费率/账户多空比/OI 24H变化)──────
export interface FuturesMetricItem {
  symbol: string // Binance 风格 'BTCUSDT'
  funding_rate: number | null
  account_long_short_ratio: number | null
  oi_change_pct_24h: number | null
}
export interface FuturesMetricsBatchResponse {
  items: FuturesMetricItem[]
}

/** 批量取多个 symbol 的合约指标 · symbols 用 Binance 风格(无斜杠)· 不在采集名单的不返回。 */
export function fetchFuturesMetricsBatch(
  binanceSymbols: string[],
  signal?: AbortSignal,
): Promise<FuturesMetricsBatchResponse> {
  if (binanceSymbols.length === 0) return Promise.resolve({ items: [] })
  const params = new URLSearchParams({ symbols: binanceSymbols.join(',') })
  return getJson<FuturesMetricsBatchResponse>(
    `/api/v1/crypto/futures/metrics-batch?${params.toString()}`,
    signal,
  )
}

// ── 布林做T结构信号(做T A-2)· 只读 A-1 的 /crypto/boll-scan 快照 ────────────────
// 字段对齐后端 schemas.crypto.BollScanItem / BollScanResponse · 全是结构描述,无买卖语义。
export interface BollScanItem {
  symbol: string // Binance 风格 'BTCUSDT'
  state: string // 6 口诀枚举值
  state_label: string // 状态中文口诀
  bias: string // 结构倾向 · 偏多 / 偏空 / 中性
  pct_b: number
  close: number
  mid: number
  upper: number
  lower: number
  change_pct_24h: number | null
  transition: boolean // 本轮是否发生状态转换
  transition_from: string | null // 转换前状态中文(仅 transition=true)
}

export interface BollScanResponse {
  as_of: string | null // 快照时间 · null = 暂无快照
  count: number
  disclaimer: string // 免责口径(红线 · 页面底部展示)
  items: BollScanItem[]
}

/** 布林做T信号列表 · 只读 A-1 快照(无快照返空列表 + as_of=null,不报错)。 */
export function fetchBollScan(signal?: AbortSignal): Promise<BollScanResponse> {
  return getJson<BollScanResponse>('/api/v1/crypto/boll-scan', signal)
}
