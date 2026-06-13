'use client'

/**
 * OAuth 到账 toast 触发器(Phase 1.5 刀B)。
 *
 * OAuth 首登时 auth.ts signIn callback 写了一次性 midas_reward cookie
 * (?ref= 查询参数 / VerifyOut 那套对 OAuth 不可用 —— 回跳后落地页才有客户端上下文)。
 * 本组件挂在根 layout,任意登录后页面 mount 即读 cookie → sonner toast → 删 cookie。
 * 一次性:删 cookie 防刷新重复弹。
 */

import { useEffect } from 'react'
import { toast } from 'sonner'

import { REWARD_COOKIE, parseRewardCookie, rewardToastMessage } from '@/lib/reward-toast'

export function RewardToastWatcher() {
  useEffect(() => {
    const m = document.cookie.match(new RegExp(`(?:^|; )${REWARD_COOKIE}=([^;]+)`))
    if (!m) return
    const { trial, invite } = parseRewardCookie(decodeURIComponent(m[1]))
    const msg = rewardToastMessage(trial, invite)
    if (msg !== null) toast.success(msg)
    // 删 cookie(一次性 · 刷新不再弹)
    document.cookie = `${REWARD_COOKIE}=; path=/; max-age=0`
  }, [])
  return null
}
