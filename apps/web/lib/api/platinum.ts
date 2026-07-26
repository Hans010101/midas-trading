/**
 * 铂金用户自助交易 API client(多账户 PR-6)· 接 PR-5a 的 /platinum/* 自助端点。
 *
 * GET  /platinum/{intelligent,managed}/status     → 我的开关/账户/活仓
 * POST /platinum/{intelligent,managed}/toggle     → 开/关我自己的(★唯一写 · 开则建影子账户)
 * GET  /platinum/{intelligent,managed}/positions  → 我的活仓 + 浮盈
 * GET  /platinum/{intelligent,managed}/history    → 我的历史平仓
 * GET  /platinum/{intelligent,managed}/stats      → 我的前向测试统计
 *
 * ★复用 admin client 的 TS interface(响应同 schema)· 只有 toggle 是写操作(无调参/手动平/reset)。
 * 🔴 fetch 透传 token(漏传 → 后端 PlatinumDep 当未登录 401)· 身份后端从 token 取,前端不传 user_id。
 */

import type {
  IntelligentHistoryPage,
  IntelligentPositionsPage,
  IntelligentStats,
  IntelligentStatus,
  StrategyParams,
} from '@/lib/api/intelligent'
import {
  INTELLIGENT_HISTORY_PAGE_SIZE,
  INTELLIGENT_POSITIONS_PAGE_SIZE,
} from '@/lib/api/intelligent'
import type {
  BatchCloseResult,
  ManagedHistoryPage,
  ManagedPositionsPage,
  ManagedStats,
  ManagedStatus,
  ManualCloseResult,
} from '@/lib/api/managed'
import {
  MANAGED_HISTORY_PAGE_SIZE,
  MANAGED_POSITIONS_PAGE_SIZE,
} from '@/lib/api/managed'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

function _h(token?: string): HeadersInit | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

async function _get<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API_BASE}/api/v1/platinum${path}`, { headers: _h(token), signal })
  if (!r.ok) throw new Error(`platinum${path} HTTP ${r.status}`)
  return (await r.json()) as T
}

async function _post<T>(path: string, token: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}/api/v1/platinum${path}`, {
    method: 'POST',
    headers: { ...(_h(token) ?? {}), 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`platinum${path} HTTP ${r.status}`)
  return (await r.json()) as T
}

// ── 智能交易(我的影子账户)──────────────────────────────────────────
export const getMyIntelligentStatus = (t: string, s?: AbortSignal) =>
  _get<IntelligentStatus>('/intelligent/status', t, s)
/** 开/关我自己的智能交易(★调用方应二次确认)。 */
export const toggleMyIntelligent = (t: string, enabled: boolean) =>
  _post<IntelligentStatus>('/intelligent/toggle', t, { enabled })
export const getMyIntelligentPositions = (
  t: string, offset = 0, limit: number = INTELLIGENT_POSITIONS_PAGE_SIZE, s?: AbortSignal,
) => _get<IntelligentPositionsPage>(`/intelligent/positions?offset=${offset}&limit=${limit}`, t, s)
export const getMyIntelligentHistory = (
  t: string, offset = 0, limit: number = INTELLIGENT_HISTORY_PAGE_SIZE, s?: AbortSignal,
) => _get<IntelligentHistoryPage>(`/intelligent/history?offset=${offset}&limit=${limit}`, t, s)
export const getMyIntelligentStats = (t: string, s?: AbortSignal) =>
  _get<IntelligentStats>('/intelligent/stats', t, s)

// ── 托管交易(我的影子账户)──────────────────────────────────────────
export const getMyManagedStatus = (t: string, s?: AbortSignal) =>
  _get<ManagedStatus>('/managed/status', t, s)
/** 开/关我自己的托管交易(★调用方应二次确认)。 */
export const toggleMyManaged = (t: string, enabled: boolean) =>
  _post<ManagedStatus>('/managed/toggle', t, { enabled })
export const getMyManagedPositions = (
  t: string, offset = 0, limit: number = MANAGED_POSITIONS_PAGE_SIZE, s?: AbortSignal,
) => _get<ManagedPositionsPage>(`/managed/positions?offset=${offset}&limit=${limit}`, t, s)
export const getMyManagedHistory = (
  t: string, offset = 0, limit: number = MANAGED_HISTORY_PAGE_SIZE, s?: AbortSignal,
) => _get<ManagedHistoryPage>(`/managed/history?offset=${offset}&limit=${limit}`, t, s)
export const getMyManagedStats = (t: string, s?: AbortSignal) =>
  _get<ManagedStats>('/managed/stats', t, s)

// ── 智能交易开仓参数 / 策略参数 / 账户操作(PR-7b/7c · per-user · 身份后端取 token)──
export const setMyIntelligentOpenMargin = (t: string, margin: number) =>
  _post<IntelligentStatus>('/intelligent/open-margin', t, { margin })
export const setMyIntelligentOpenLeverage = (t: string, leverage: number) =>
  _post<IntelligentStatus>('/intelligent/open-leverage', t, { leverage })
export const setMyIntelligentMaxPositions = (t: string, max_positions: number) =>
  _post<IntelligentStatus>('/intelligent/max-positions', t, { max_positions })
export const getMyIntelligentStrategyParams = (t: string, s?: AbortSignal) =>
  _get<StrategyParams>('/intelligent/strategy-params', t, s)
export const setMyIntelligentStrategyParams = (t: string, params: StrategyParams) =>
  _post<StrategyParams>('/intelligent/strategy-params', t, params)
/** 清零我的智能影子账户(★调用方应二次确认)。 */
export const resetMyIntelligent = (t: string) =>
  _post<IntelligentStatus>('/intelligent/account/reset', t)
export const setMyIntelligentCapital = (t: string, amount: number) =>
  _post<IntelligentStatus>('/intelligent/account/capital', t, { amount })

// ── 托管交易开仓参数 / 账户操作 / 平仓(PR-7b/7c · ★决策B 无 exit/tp 自助·平仓参数全局)──
export const setMyManagedOpenMargin = (t: string, margin: number) =>
  _post<ManagedStatus>('/managed/open-margin', t, { margin })
export const setMyManagedOpenLeverage = (t: string, leverage: number) =>
  _post<ManagedStatus>('/managed/open-leverage', t, { leverage })
export const setMyManagedMaxPositions = (t: string, max_positions: number) =>
  _post<ManagedStatus>('/managed/max-positions', t, { max_positions })
/** 清零我的托管影子账户(★调用方应二次确认)。 */
export const resetMyManaged = (t: string) =>
  _post<ManagedStatus>('/managed/account/reset', t)
export const setMyManagedCapital = (t: string, amount: number) =>
  _post<ManagedStatus>('/managed/account/capital', t, { amount })
/** 手动平我的某托管活仓(★越权:仓不属我后端返 not_found)。 */
export const closeMyManagedPosition = (t: string, positionId: number) =>
  _post<ManualCloseResult>(`/managed/positions/${positionId}/close`, t)
/** 一键平我的所有托管活仓(★调用方应二次确认)。 */
export const closeAllMyManaged = (t: string) =>
  _post<BatchCloseResult>('/managed/positions/close-all', t)

// ── 方向过滤器(PR-8 · per-user · 智能双开关 / 托管单开关)──────────────────
/** ★设我的智能方向过滤(which=long/short · on)。 */
export const setMyIntelligentAllowDirection = (
  t: string, which: 'long' | 'short', on: boolean,
) => _post<IntelligentStatus>('/intelligent/allow-direction', t, { which, on })
/** ★设我的托管允许开多(on · 托管恒做多·OFF=不开新仓)。 */
export const setMyManagedAllowLong = (t: string, on: boolean) =>
  _post<ManagedStatus>('/managed/allow-long', t, { on })
