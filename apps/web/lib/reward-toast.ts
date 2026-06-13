/**
 * 试用/邀请到账感知文案(Phase 1.5 刀B)· vitest 可测。
 *
 * 后端 VerifyOut / OAuthGoogleOut 的 trial_granted / invite_rewarded 两 flag
 * → 合并成一句感知文案。两者可同时(受邀新用户:试用 7 + 邀请 15)。
 * 🔴 文案诚实:天数如实(7 / 15),不夸大。
 */

export function rewardToastMessage(trialGranted: boolean, inviteRewarded: boolean): string | null {
  if (trialGranted && inviteRewarded) {
    return '已获赠 7 天 Pro 试用 · 邀请奖励 +15 天已到账'
  }
  if (trialGranted) return '已获赠 7 天 Pro 试用'
  if (inviteRewarded) return '邀请奖励已到账 · Pro +15 天'
  return null
}

/** 一次性奖励 cookie(OAuth 路径用 · signIn callback 写,落地 watcher 读后删)。 */
export const REWARD_COOKIE = 'midas_reward'

/** "trial,invite" / "trial" / "invite" → 两 flag。 */
export function parseRewardCookie(raw: string | null | undefined): {
  trial: boolean
  invite: boolean
} {
  const parts = (raw ?? '').split(',').map((s) => s.trim())
  return { trial: parts.includes('trial'), invite: parts.includes('invite') }
}

export function buildRewardCookieValue(
  trialGranted: boolean,
  inviteRewarded: boolean,
): string | null {
  const parts: string[] = []
  if (trialGranted) parts.push('trial')
  if (inviteRewarded) parts.push('invite')
  return parts.length > 0 ? parts.join(',') : null
}
