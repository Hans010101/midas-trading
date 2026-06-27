/**
 * 托管交易(策略前向测试)· admin API client(托管交易 PR-4)。
 *
 * GET  /admin/managed/status     → 开关/账户/现金/活仓
 * POST /admin/managed/toggle     → 开/关(★默认 OFF · 开则建账户)
 * GET  /admin/managed/positions  → 当前活仓 + 浮盈
 * GET  /admin/managed/history    → 历史平仓明细
 * GET  /admin/managed/stats      → 前向测试统计
 *
 * 🔴 全 admin 端点(后端 AdminDep 403)· 🔴纯虚拟绝不真单 · fetch 透传 token。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface ManagedStatus {
  enabled: boolean
  account_ready: boolean
  cash_balance: number
  initial_capital: number
  open_positions: number
}

export interface ManagedPosition {
  symbol: string
  leverage: number
  entry_price: number
  quantity: number
  margin: number
  opened_at: string
  mark: number | null
  unrealized_pnl: number | null
  unrealized_pct: number | null
}

export interface ManagedTrade {
  symbol: string
  leverage: number
  entry_price: number
  exit_price: number
  quantity: number
  pnl_usdt: number
  pnl_pct: number
  close_reason: string | null
  opened_at: string
  closed_at: string | null
  hold_seconds: number
}

export interface ManagedStats {
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  total_pnl: number
  avg_pnl: number
  profit_factor: number
  max_drawdown: number
  by_reason: { tp: number; signal: number; timeout: number }
}

function _h(token?: string): HeadersInit | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

async function _get<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API_BASE}/api/v1/admin/managed${path}`, { headers: _h(token), signal })
  if (!r.ok) throw new Error(`managed${path} HTTP ${r.status}`)
  return (await r.json()) as T
}

export const getManagedStatus = (t: string, s?: AbortSignal) =>
  _get<ManagedStatus>('/status', t, s)
export const getManagedPositions = (t: string, s?: AbortSignal) =>
  _get<ManagedPosition[]>('/positions', t, s)
export const getManagedHistory = (t: string, s?: AbortSignal) =>
  _get<ManagedTrade[]>('/history', t, s)
export const getManagedStats = (t: string, s?: AbortSignal) =>
  _get<ManagedStats>('/stats', t, s)

/** 开/关托管交易(★开 = 启动策略前向测试 · 调用方应二次确认)。 */
export async function toggleManaged(token: string, enabled: boolean): Promise<ManagedStatus> {
  const r = await fetch(`${API_BASE}/api/v1/admin/managed/toggle`, {
    method: 'POST',
    headers: { ...(_h(token) ?? {}), 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!r.ok) throw new Error(`managed toggle HTTP ${r.status}`)
  return (await r.json()) as ManagedStatus
}
