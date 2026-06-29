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
  account_value: number // ★账户总价值(权益·浮动)= 现金 + Σ浮盈亏 · 复用引擎算法
  initial_capital: number
  cash_balance: number
  open_positions: number
  open_margin: number // ★每单本金(U·可调 10-10000·默认 100)
  open_leverage: number // ★杠杆(可调 1-20·默认 5·不影响 ATR 止损止盈价)
  max_positions: number // ★最大总持仓数(可调·默认 50·到上限不开新)
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

export interface IntelligentPositionsPage {
  items: IntelligentPosition[]
  total: number // ★全部活仓数(前端算总页数)
}

export interface IntelligentHistoryPage {
  items: IntelligentTrade[]
  total: number // ★全部历史单数
}

export const INTELLIGENT_POSITIONS_PAGE_SIZE = 100
export const INTELLIGENT_HISTORY_PAGE_SIZE = 50

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
/** ★活仓分页:offset/limit(默认每页 100)· 返回 {items, total}。 */
export const getIntelligentPositions = (
  t: string,
  offset = 0,
  limit: number = INTELLIGENT_POSITIONS_PAGE_SIZE,
  s?: AbortSignal,
) => _get<IntelligentPositionsPage>(`/positions?offset=${offset}&limit=${limit}`, t, s)
/** ★历史分页:offset/limit(默认每页 50·照搬托管 PR#82)· 返回 {items, total}。 */
export const getIntelligentHistory = (
  t: string,
  offset = 0,
  limit: number = INTELLIGENT_HISTORY_PAGE_SIZE,
  s?: AbortSignal,
) => _get<IntelligentHistoryPage>(`/history?offset=${offset}&limit=${limit}`, t, s)
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

/** ★设每单本金(U·10-10000 · 即时生效)。 */
export const setIntelligentOpenMargin = (token: string, margin: number) =>
  _post<IntelligentStatus>('/open-margin', token, { margin })

/** ★设杠杆(1-20 · 即时生效 · 不影响 ATR 止损止盈价)。 */
export const setIntelligentOpenLeverage = (token: string, leverage: number) =>
  _post<IntelligentStatus>('/open-leverage', token, { leverage })

/** ★设最大总持仓数(>0 · 即时生效)。 */
export const setIntelligentMaxPositions = (token: string, maxPositions: number) =>
  _post<IntelligentStatus>('/max-positions', token, { max_positions: maxPositions })
