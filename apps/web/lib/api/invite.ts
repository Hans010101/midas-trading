/**
 * 邀请 API client(Phase 1.5 刀B)· GET /invite/me · 照 quota.ts Bearer 范式。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface InviteMe {
  code: string
  invite_url: string
  invited_count: number
  rewarded_count: number
  earned_days: number
}

export async function fetchInviteMe(token: string, signal?: AbortSignal): Promise<InviteMe> {
  const r = await fetch(`${API_BASE}/api/v1/invite/me`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new Error(`InviteApi HTTP ${r.status}`)
  return (await r.json()) as InviteMe
}
