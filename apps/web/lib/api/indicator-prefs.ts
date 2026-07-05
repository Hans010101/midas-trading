/**
 * 指标偏好 API client(做T线前端 · 读写 #158 后端 User.indicator_prefs)。
 *
 * GET/PATCH /api/v1/user/indicator-prefs · 三键 bollinger/chan/day_trade(布尔)·
 * NULL/部分由后端合并默认(布林 ON · 缠论 ON · 做T OFF)返全量。
 * ★本期前端只用 day_trade(暗发布门控:加密市场页「做T信号」榜单仅 day_trade=ON 可见);
 *   bollinger/chan 后端已存(默认 ON)但前端本期不暴露 toggle(避免与 cookie 版详情页偏好重叠)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface IndicatorPrefs {
  bollinger: boolean
  chan: boolean
  day_trade: boolean
}

/** PATCH 部分更新:只传要改的键(后端只认已知键·脏键忽略)。 */
export type IndicatorPrefsUpdate = Partial<IndicatorPrefs>

export class IndicatorPrefsApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`IndicatorPrefsApi ${status}: ${detail}`)
    this.name = 'IndicatorPrefsApiError'
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

export async function fetchIndicatorPrefs(
  token: string,
  signal?: AbortSignal,
): Promise<IndicatorPrefs> {
  const r = await fetch(`${API_BASE}/api/v1/user/indicator-prefs`, {
    headers: authHeaders(token),
    signal,
  })
  if (!r.ok) throw new IndicatorPrefsApiError(r.status, await readDetail(r))
  return (await r.json()) as IndicatorPrefs
}

export async function updateIndicatorPrefs(
  token: string,
  payload: IndicatorPrefsUpdate,
): Promise<IndicatorPrefs> {
  const r = await fetch(`${API_BASE}/api/v1/user/indicator-prefs`, {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new IndicatorPrefsApiError(r.status, await readDetail(r))
  return (await r.json()) as IndicatorPrefs
}
