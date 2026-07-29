/**
 * X 营销 · 每日推文后台 API client(阶段4a · PR-3)。
 *
 * GET  /api/v1/admin/x-tweets            → 今日推文列表(24h · 含门禁结果)
 * GET  /api/v1/admin/x-tweets/{id}       → 单条详情
 * POST /api/v1/admin/x-tweets/generate   → 触发生成(异步 · Celery)
 *
 * 🔴 全 admin 端点(后端 AdminDep 403 强制)· fetch 透传 session token。
 * ★ 止于展示 + 触发生成 · 不发 X(发布=4b)· 截图字段 image_path 现阶段为 null(PR-4 填)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export interface XTweetDispatchItem {
  platform: string
  status: string // pending / success / failed
  url: string | null
  error: string | null
  source: string // 发布来源 · manual 人工 / auto 自动托管(自动托管 PR-4 审计)
}

export interface XTweetItem {
  id: number
  symbol: string
  bias: string
  tweet_text: string
  compliance_passed: boolean
  compliance_reason: string | null
  status: string
  image_path: string | null
  created_at: string
  auto_drafted: boolean // ★自动托管起草(待补发素材标识 · 频率调整)
  has_url: boolean // ★正文含 URL(发 X 贵十几倍 · 成本提醒 · 非门禁否决)
  gen_style: string // ★内容风格/平台(default 币安长文 / x_short X 短推)
  content_type: 'market_analysis' | 'news' | 'whale' | 'unlock'
  source_event_id: number | null
  dispatches: XTweetDispatchItem[] // 各平台发布状态(发布层 PR-3)
}

export interface XTweetListOut {
  items: XTweetItem[]
  total: number
}

export interface XTweetGenerateOut {
  status: string
  message: string
}

export interface XTweetPublishOut {
  dispatch_id: number
  platform: string
  status: string
  message: string
}

function _authHeaders(token?: string): HeadersInit | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

export async function fetchXTweets(token: string, signal?: AbortSignal): Promise<XTweetListOut> {
  const r = await fetch(`${API_BASE}/api/v1/admin/x-tweets`, {
    headers: _authHeaders(token),
    signal,
  })
  if (!r.ok) throw new Error(`x-tweets list HTTP ${r.status}`)
  return (await r.json()) as XTweetListOut
}

/**
 * 触发生成今日推文(异步 · 后端 enqueue Celery,约数十秒后列表刷新可见)。
 * style:default=币安广场长文 / x_short=X 短推(≤110 字·冷静体检口吻)。
 */
export async function generateXTweets(
  token: string,
  style: 'default' | 'x_short' = 'default',
): Promise<XTweetGenerateOut> {
  const r = await fetch(`${API_BASE}/api/v1/admin/x-tweets/generate?style=${style}`, {
    method: 'POST',
    headers: _authHeaders(token),
  })
  if (!r.ok) throw new Error(`x-tweets generate HTTP ${r.status}`)
  return (await r.json()) as XTweetGenerateOut
}

/**
 * 取推文截图(★端点是 AdminDep,<img src> 不能带 Bearer → authed fetch 拿 blob,
 * 调用方 URL.createObjectURL 给 <img>)· 无截图 404 → 抛错(调用方显占位)。
 */
export async function fetchXTweetImage(token: string, id: number): Promise<Blob> {
  const r = await fetch(`${API_BASE}/api/v1/admin/x-tweets/${id}/image`, {
    headers: _authHeaders(token),
  })
  if (!r.ok) throw new Error(`x-tweets image HTTP ${r.status}`)
  return await r.blob()
}

/**
 * 发布到指定平台(★admin 单次显式 · 异步 enqueue · 后端硬校验门禁通过/幂等/频率)。
 * 返回 dispatch 状态(pending)· 失败抛错(含后端 detail:门禁未过/未配置/已发过/频率超)。
 */
export async function publishXTweet(
  token: string,
  id: number,
  platform: string,
): Promise<XTweetPublishOut> {
  const r = await fetch(`${API_BASE}/api/v1/admin/x-tweets/${id}/publish`, {
    method: 'POST',
    headers: { ...(_authHeaders(token) ?? {}), 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform }),
  })
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as
      | { detail?: string }
      | null
    throw new Error(detail?.detail ?? `x-tweets publish HTTP ${r.status}`)
  }
  return (await r.json()) as XTweetPublishOut
}
