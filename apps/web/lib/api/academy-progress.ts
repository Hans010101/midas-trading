/**
 * 训练营学习进度 API client · B 期刀1。
 *
 * GET    /api/v1/academy/progress            → 当前用户已完成 slug + 各阶完成数(未登录返空)
 * POST   /api/v1/academy/progress/complete   → 标记学完(幂等 · 强制登录)
 * DELETE /api/v1/academy/progress/complete   → 取消标记(幂等 · toggle 用)
 *
 * 🔴 纯展示型学习数据 · 与交易/支付/会员零关系。
 * ★ 进度存后端(不用 localStorage)· fetch 透传 session token(后端按用户存)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface AcademyProgress {
  completed_slugs: string[]
  /** 各阶已完成数(进度 X)· 阶 slug → count */
  by_stage: Record<string, number>
  /** 各阶文章总数(进度 Y · 后端目录权威)· 阶 slug → count */
  stage_totals: Record<string, number>
  total_completed: number
  total_articles: number
}

function _authHeaders(token?: string): HeadersInit | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

export async function fetchAcademyProgress(
  token?: string,
  signal?: AbortSignal,
): Promise<AcademyProgress> {
  const r = await fetch(`${API_BASE}/api/v1/academy/progress`, {
    headers: _authHeaders(token),
    signal,
  })
  if (!r.ok) throw new Error(`academy progress HTTP ${r.status}`)
  return (await r.json()) as AcademyProgress
}

/** 标记学完 · 需登录(无 token 直接抛,调用方应先判登录态)。 */
export async function markArticleComplete(slug: string, token: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/academy/progress/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ article_slug: slug }),
  })
  if (!r.ok) throw new Error(`mark complete HTTP ${r.status}`)
}

/** 取消标记 · 需登录。 */
export async function unmarkArticleComplete(slug: string, token: string): Promise<void> {
  const url = `${API_BASE}/api/v1/academy/progress/complete?article_slug=${encodeURIComponent(slug)}`
  const r = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!r.ok) throw new Error(`unmark complete HTTP ${r.status}`)
}
