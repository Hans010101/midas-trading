/**
 * 研究室回测 API client · P1-4d(ADR 0038 · authed-only)。
 * 照 lib/api/bot-preset.ts 的 authed 范式:authHeaders(token) + 自定义 Error 类 + readDetail。
 *
 * 🔴 红线:纯研究记录的【只读展示 + 发起】· 绝不下单 / 撮合 / 真实交易 · market 锁 crypto。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'
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
  commission_rate?: number
  slippage_bps?: number
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

/**
 * vibe calc_metrics 的 16 个标量指标(metrics.csv 单行)。
 * ★ 量纲契约(ADR 0040):本 interface 的收益/回撤/胜率类全是【比率】(0.1=10% · 前端 fmtPct ×100);
 *   与 Trade.return_pct(百分比数值)量纲不同 —— 同一引擎两套量纲,选错格式化函数差 100 倍。
 */
export interface BacktestMetrics {
  final_value: number // 绝对额(报价币 USDT)· fmtNum
  total_return: number // 比率(0.1=10% · P1-3 实测 -0.185=-18.5%)· fmtPct
  annual_return: number // 比率 · fmtPct
  max_drawdown: number // 比率(≤0)· fmtPct
  sharpe: number // 无量纲比值 · fmtRatio
  calmar: number // 无量纲比值 · fmtRatio
  sortino: number // 无量纲比值 · fmtRatio
  win_rate: number // 比率(0.55=55%)· fmtPct
  profit_loss_ratio: number // 无量纲比值 · fmtRatio
  profit_factor: number // 无量纲比值 · fmtRatio
  max_consecutive_loss: number // 整数计数 · fmtInt
  avg_holding_days: number // 天(推断+弱印证 · 见量纲审计报告)
  trade_count: number // 整数计数 · 完整回合(开+平 · 17 回合=34 条买卖腿)· fmtInt
  benchmark_return: number // 比率 · fmtPct
  excess_return: number // 比率 · fmtPct
  information_ratio: number // 无量纲比值 · fmtRatio
}

/** equity.csv 一行。数值列全是【比率/绝对额】(与 metrics 同侧,无百分比数值)。 */
export interface EquityPoint {
  timestamp: string // 日期串("2025-01-18" · 1d 粒度)
  equity: number // 绝对额(策略权益)
  drawdown: number // 比率 ≤0(真机实测 -0.0201=回撤2.01% · 前端 ×100)
  benchmark_equity: number // 绝对额(买入持有基准)
  ret: number // 比率(推断 · 前端未渲染 · 上屏前须真机核原值)
  active_ret: number // 比率(推断 · 前端未渲染 · 上屏前须真机核原值)
}

/** trades.csv 一行(一条买卖腿 · 17 回合=34 条)。★return_pct 量纲与 metrics 不同! */
export interface Trade {
  timestamp: string // 日期串
  code: string // 'BTCUSDT'(无斜杠 vibe code)
  side: string // 'buy'=开仓腿 / 'sell'=平仓腿(当前 SMA 纯多头;若放开做空策略此语义需重审)
  price: number // 绝对价 · fmtNum
  qty: number // base 币数量(当前裸渲染 · 长尾显示待打磨,见审计报告)
  reason: string // 可读原因('entry' 等)
  pnl: number // 绝对额(报价币 · 真机实测 -27547.76)· fmtNum · 开仓腿无意义显「—」
  holding_days: number // 天(推断+弱印证)
  return_pct: number // ★【百分比数值】(-2.76=-2.76% · 真机实测)· fmtPctNum 绝不 ×100(P1-4e.fix)
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
    /** 会员刀2:429 结构化 detail 原样保留 */
    public readonly rawDetail: unknown = null,
  ) {
    super(`BacktestApi ${status}: ${detail}`)
    this.name = 'BacktestApiError'
  }
}

async function readDetail(resp: Response): Promise<{ text: string; raw: unknown }> {
  try {
    const body = (await resp.json()) as { detail?: unknown }
    return {
      text: typeof body.detail === 'string' ? body.detail : `HTTP ${resp.status}`,
      raw: body.detail ?? null,
    }
  } catch {
    return { text: `HTTP ${resp.status}`, raw: null }
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
  if (!r.ok) {
    const d = await readDetail(r)
    throw new BacktestApiError(r.status, d.text, d.raw)
  }
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
  if (!r.ok) {
    const d = await readDetail(r)
    throw new BacktestApiError(r.status, d.text, d.raw)
  }
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
  if (!r.ok) {
    const d = await readDetail(r)
    throw new BacktestApiError(r.status, d.text, d.raw)
  }
  return (await r.json()) as BacktestRunResponse
}
