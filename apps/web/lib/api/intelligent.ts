/**
 * 智能交易(策略前向测试)· admin API client(智能交易 PR-6)。
 *
 * GET  /admin/intelligent/status     → 开关/账户/现金/活仓
 * POST /admin/intelligent/toggle     → 开/关(★默认 OFF · 开则建账户)
 * POST /admin/intelligent/account/reset    → 清零重来
 * POST /admin/intelligent/account/capital  → 改起始资金
 * GET  /admin/intelligent/positions  → 当前活仓 + 浮盈 + 共振(★做多做空)
 * GET  /admin/intelligent/history    → 历史平仓明细(★做多做空)
 * GET  /admin/intelligent/stats      → 前向测试统计(★by_side 做多做空)
 *
 * 🔴 全 admin 端点(后端 AdminDep 403)· 🔴纯虚拟绝不真单 · fetch 透传 token。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface IntelligentStatus {
  enabled: boolean
  account_ready: boolean
  initial_capital: number
  cash_balance: number
  open_positions: number
}

export interface IntelligentPosition {
  id: number
  symbol: string
  side: string // ★long / short(做多做空)
  leverage: number
  entry_price: number
  quantity: number
  margin: number
  opened_at: string
  mark: number | null
  unrealized_pnl: number | null
  unrealized_pct: number | null
  stop_price: number | null // ATR 止损价
  tp_price: number | null // 2:1 止盈价
  signals: { score?: number; contributions?: Record<string, number> } | null // ★共振明细
}

export interface IntelligentTrade {
  symbol: string
  side: string // ★long / short
  leverage: number
  entry_price: number
  exit_price: number
  quantity: number
  pnl_usdt: number
  pnl_pct: number
  close_reason: string | null // stop_loss / take_profit / signal_reversal
  opened_at: string
  closed_at: string | null
  hold_seconds: number
}

export interface IntelligentStats {
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  total_pnl: number
  avg_pnl: number
  profit_factor: number
  max_drawdown: number
  by_reason: { stop_loss: number; take_profit: number; signal_reversal: number }
  by_side: { long: number; short: number } // ★做多做空笔数
}

function _h(token?: string): HeadersInit | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

async function _get<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API_BASE}/api/v1/admin/intelligent${path}`, { headers: _h(token), signal })
  if (!r.ok) throw new Error(`intelligent${path} HTTP ${r.status}`)
  return (await r.json()) as T
}

export const getIntelligentStatus = (t: string, s?: AbortSignal) =>
  _get<IntelligentStatus>('/status', t, s)
export const getIntelligentPositions = (t: string, s?: AbortSignal) =>
  _get<IntelligentPosition[]>('/positions', t, s)
export const getIntelligentHistory = (t: string, s?: AbortSignal) =>
  _get<IntelligentTrade[]>('/history', t, s)
export const getIntelligentStats = (t: string, s?: AbortSignal) =>
  _get<IntelligentStats>('/stats', t, s)

async function _post<T>(path: string, token: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}/api/v1/admin/intelligent${path}`, {
    method: 'POST',
    headers: { ...(_h(token) ?? {}), 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`intelligent${path} HTTP ${r.status}`)
  return (await r.json()) as T
}

/** 开/关智能交易(★开 = 启动策略前向测试 · 调用方应二次确认)。 */
export const toggleIntelligent = (token: string, enabled: boolean) =>
  _post<IntelligentStatus>('/toggle', token, { enabled })

/** ★清零重来(删智能账户持仓+历史 · cash 重置初始 · 调用方应二次确认)。 */
export const resetIntelligentAccount = (token: string) =>
  _post<IntelligentStatus>('/account/reset', token)

/** ★改起始资金(>0 · 清持仓 + 用新资金重来)。 */
export const setIntelligentCapital = (token: string, amount: number) =>
  _post<IntelligentStatus>('/account/capital', token, { amount })
