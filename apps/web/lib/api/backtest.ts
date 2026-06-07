/**
 * 研究室回测 API client · P1-4d(ADR 0038 · authed-only)。
 * 照 lib/api/bot-preset.ts 的 authed 范式:authHeaders(token) + 自定义 Error 类 + readDetail。
 *
 * 🔴 红线:纯研究记录的【只读展示 + 发起】· 绝不下单 / 撮合 / 真实交易 · market 锁 crypto。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const PREFIX = '/api/v1/backtest'

export type BacktestStatus = 'pending' | 'done' | 'error'
export type BacktestPeriod = '1m' | '5m' | '15m' | '30m' | '1h' | '1d' | '1w'

export interface BacktestCreateRequest {
  symbol: string
  start: string // YYYY-MM-DD
  end: string // YYYY-MM-DD
  market?: 'crypto' // 当前仅 crypto(后端 Literal)
  period?: BacktestPeriod
  sma_fast?: number
  sma_slow?: number
  initial_cash?: number
  leverage?: number
}

export interface BacktestCreateResponse {
  id: number
  status: BacktestStatus
}

export interface BacktestRunListItem {
  id: number
  symbol: string
  market: string
  period: string
  start_date: string
  end_date: string
  status: BacktestStatus
  created_at: string
}

/** vibe calc_metrics 的 16 个标量指标(都是 number;max_consecutive_loss / trade_count 是整数)。 */
export interface BacktestMetrics {
  final_value: number
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe: number
  calmar: number
  sortino: number
  win_rate: number
  profit_loss_ratio: number
  profit_factor: number
  max_consecutive_loss: number
  avg_holding_days: number
  trade_count: number
  benchmark_return: number
  excess_return: number
  information_ratio: number
}

export interface EquityPoint {
  timestamp: string
  equity: number
  drawdown: number
  benchmark_equity: number
  ret: number
  active_ret: number
}

export interface Trade {
  timestamp: string
  code: string
  side: string
  price: number
  qty: number
  reason: string
  pnl: number
  holding_days: number
  return_pct: number
}

export interface BacktestRunResponse {
  id: number
  symbol: string
  market: string
  period: string
  start_date: string
  end_date: string
  params_json: Record<string, unknown>
  status: BacktestStatus
  metrics_json: BacktestMetrics | null
  equity_json: EquityPoint[] | null
  trades_json: Trade[] | null
  run_card_json: Record<string, unknown> | null
  error: string | null
  created_at: string
  updated_at: string
}

export class BacktestApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`BacktestApi ${status}: ${detail}`)
    this.name = 'BacktestApiError'
  }
}

async function readDetail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : `HTTP ${resp.status}`
  } catch {
    return `HTTP ${resp.status}`
  }
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

/** POST /api/v1/backtest · 发起一次回测 → { id, status:"pending" }。 */
export async function createBacktest(
  token: string,
  body: BacktestCreateRequest,
): Promise<BacktestCreateResponse> {
  const r = await fetch(`${API_BASE}${PREFIX}`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new BacktestApiError(r.status, await readDetail(r))
  return (await r.json()) as BacktestCreateResponse
}

/** GET /api/v1/backtest · 本人回测历史(created_at 倒序)。 */
export async function listBacktests(
  token: string,
  limit = 50,
  signal?: AbortSignal,
): Promise<BacktestRunListItem[]> {
  const r = await fetch(`${API_BASE}${PREFIX}?limit=${limit}`, {
    headers: authHeaders(token),
    signal,
  })
  if (!r.ok) throw new BacktestApiError(r.status, await readDetail(r))
  return (await r.json()) as BacktestRunListItem[]
}

/** GET /api/v1/backtest/{id} · 单条 full-data(含 metrics/equity/trades/run_card)· 越权 404。 */
export async function getBacktest(
  token: string,
  id: number,
  signal?: AbortSignal,
): Promise<BacktestRunResponse> {
  const r = await fetch(`${API_BASE}${PREFIX}/${id}`, {
    headers: authHeaders(token),
    signal,
  })
  if (!r.ok) throw new BacktestApiError(r.status, await readDetail(r))
  return (await r.json()) as BacktestRunResponse
}
