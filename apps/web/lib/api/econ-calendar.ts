/**
 * 财经日历 API client(PR-A · 公开只读 · 无 token)。
 *
 *   GET /api/v1/econ/calendar · 今天起全部宏观事件日程 + 保鲜元信息
 *
 * 🔴 红线:本模块只做取数,零解读文案;页面展示模板同样纯静态
 * (apps/api tests/services/test_econ_calendar_page.py 机器钉死)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export interface EconEvent {
  event_key: string
  event_type: string
  title: string
  markets: string[]
  importance: number // 3/2/1 星级
  scheduled_at: string // ISO · tz-aware
  time_confirmed: boolean // false = 窗口/惯例占位(展示标「时刻待定」)
  source: string // fed_json / bea_json / rule / seed
}

export interface EconJobStatus {
  source: string
  last_success: string | null
  age_seconds: number | null
  stale: boolean
}

export interface EconCalendarResponse {
  events: EconEvent[]
  sources: EconJobStatus[]
  /** 数据更新时间 = 采集任务 last-run 成功时间(保鲜口径 · 非 max(事件ts)) */
  updated_at: string | null
  any_stale: boolean
}

export class EconCalendarApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail)
    this.name = 'EconCalendarApiError'
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
    throw new EconCalendarApiError(r.status, detail)
  }
  return (await r.json()) as T
}

export function fetchEconCalendar(signal?: AbortSignal): Promise<EconCalendarResponse> {
  return getJson<EconCalendarResponse>('/api/v1/econ/calendar', signal)
}
