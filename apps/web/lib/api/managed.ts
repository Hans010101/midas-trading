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
  account_value: number // ★账户价值(权益·浮动)= 现金 + Σ浮盈浮亏 · 和活仓浮盈对得上
  available_funds: number // ★可用资金 = 账户价值 − 已占用保证金
  occupied_margin: number // 已占用保证金
  cash_balance: number // 账户现金(只扣手续费)
  initial_capital: number
  open_positions: number
  exit_tp: boolean // ★止盈平仓开关
  exit_signal: boolean // ★信号转换平仓开关
  exit_timeout: boolean // ★超时平仓开关(三个全关=仅手动平)
  tp_pct: number // ★止盈目标(盈利%·默认100·仅止盈开关开时生效·价涨幅%=盈利%÷杠杆)
  open_margin: number // ★每单本金(U·可调 10-10000·默认 100)
  open_leverage: number // ★杠杆(可调 1-20·默认 5)
  max_positions: number // ★最大总持仓数(可调·默认 50·到上限不开新)
}

export interface ManagedPosition {
  id: number // ★position_id(手动平单用)
  symbol: string
  leverage: number
  entry_price: number
  quantity: number
  margin: number
  opened_at: string
  mark: number | null
  unrealized_pnl: number | null
  unrealized_pct: number | null
  bias: string | null // ★维持的信号(偏多/偏空/中性 · 不在快照=维持上一次)
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
  by_reason: { tp: number; signal: number; timeout: number; manual: number }
}

export interface ManualCloseResult {
  status: string
  symbol: string | null
  realized_pnl: number | null
}

export interface ManagedHistoryPage {
  items: ManagedTrade[]
  total: number // ★全部历史单数(前端算总页数)
}

export interface ManagedPositionsPage {
  items: ManagedPosition[]
  total: number // ★全部活仓数(前端算总页数)
}

export interface BatchCloseResult {
  status: string
  closed: number // 实际平掉数
  total: number // 本次扫到的活仓数
}

export const MANAGED_HISTORY_PAGE_SIZE = 50
export const MANAGED_POSITIONS_PAGE_SIZE = 100

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
/** ★活仓分页:offset/limit(默认每页 100)· 返回 {items, total}。 */
export const getManagedPositions = (
  t: string,
  offset = 0,
  limit: number = MANAGED_POSITIONS_PAGE_SIZE,
  s?: AbortSignal,
) => _get<ManagedPositionsPage>(`/positions?offset=${offset}&limit=${limit}`, t, s)
/** ★历史分页:offset/limit(默认每页 50)· 返回 {items, total}(total 算总页数)。 */
export const getManagedHistory = (
  t: string,
  offset = 0,
  limit: number = MANAGED_HISTORY_PAGE_SIZE,
  s?: AbortSignal,
) => _get<ManagedHistoryPage>(`/history?offset=${offset}&limit=${limit}`, t, s)
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

/** ★手动平单(人工应急出口 · 调用方应二次确认)· 后端调 route_close_perp 记 manual。 */
export async function closeManagedPosition(
  token: string,
  positionId: number,
): Promise<ManualCloseResult> {
  const r = await fetch(`${API_BASE}/api/v1/admin/managed/positions/${positionId}/close`, {
    method: 'POST',
    headers: _h(token),
  })
  if (!r.ok) throw new Error(`managed close HTTP ${r.status}`)
  return (await r.json()) as ManualCloseResult
}

/** ★一键平掉所有托管活仓(★强制二次确认 · 调用方必须确认)· 后端逐个 route_close_perp 记 manual。 */
export async function closeAllManagedPositions(token: string): Promise<BatchCloseResult> {
  const r = await fetch(`${API_BASE}/api/v1/admin/managed/positions/close-all`, {
    method: 'POST',
    headers: _h(token),
  })
  if (!r.ok) throw new Error(`managed close-all HTTP ${r.status}`)
  return (await r.json()) as BatchCloseResult
}

/** ★设单个平仓条件开关(tp/signal/timeout · 即时生效)· 返回最新状态。 */
export async function setManagedExitSwitch(
  token: string,
  which: 'tp' | 'signal' | 'timeout',
  on: boolean,
): Promise<ManagedStatus> {
  const r = await fetch(`${API_BASE}/api/v1/admin/managed/exit-switch`, {
    method: 'POST',
    headers: { ...(_h(token) ?? {}), 'Content-Type': 'application/json' },
    body: JSON.stringify({ which, on }),
  })
  if (!r.ok) throw new Error(`managed exit-switch HTTP ${r.status}`)
  return (await r.json()) as ManagedStatus
}

/** ★设止盈目标(盈利%·>0 · 即时生效)· 返回最新状态。 */
export async function setManagedTpPct(token: string, pct: number): Promise<ManagedStatus> {
  const r = await fetch(`${API_BASE}/api/v1/admin/managed/exit-tp-pct`, {
    method: 'POST',
    headers: { ...(_h(token) ?? {}), 'Content-Type': 'application/json' },
    body: JSON.stringify({ pct }),
  })
  if (!r.ok) throw new Error(`managed exit-tp-pct HTTP ${r.status}`)
  return (await r.json()) as ManagedStatus
}

async function _postManaged(path: string, token: string, body: unknown): Promise<ManagedStatus> {
  const r = await fetch(`${API_BASE}/api/v1/admin/managed${path}`, {
    method: 'POST',
    headers: { ...(_h(token) ?? {}), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`managed${path} HTTP ${r.status}`)
  return (await r.json()) as ManagedStatus
}

/** ★设每单本金(U·10-10000 · 即时生效)。 */
export const setManagedOpenMargin = (token: string, margin: number) =>
  _postManaged('/open-margin', token, { margin })

/** ★设杠杆(1-20 · 即时生效)。 */
export const setManagedOpenLeverage = (token: string, leverage: number) =>
  _postManaged('/open-leverage', token, { leverage })

/** ★设最大总持仓数(>0 · 即时生效)。 */
export const setManagedMaxPositions = (token: string, maxPositions: number) =>
  _postManaged('/max-positions', token, { max_positions: maxPositions })
