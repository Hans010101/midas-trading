'use client'

/**
 * 顶栏语言快捷切换(i18n cookie-locale · 决策 A)· 中↔EN 一键切。
 *
 * 显示【要切到的目标语言】(中文界面显 EN · 英文界面显 中)· 点击写 NEXT_LOCALE cookie +
 *   router.refresh()(服务端组件按新 cookie 重渲 · URL 恒不变 · 无 redirect)。
 * ★访客(未登录)也能切(纯 cookie)· 登录用户额外写回后端 language_pref 跨设备同步。
 * ★挂载前渲染占位,避免 SSR/首帧布局跳动(仿 theme-toggle)。
 */

import { Languages } from 'lucide-react'
import { useLocale } from 'next-intl'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { useEffect, useState } from 'react'

import { useSetLanguage } from '@/hooks/use-me'
import { setLocaleCookie } from '@/lib/i18n/locale-cookie'

export function LanguageToggle() {
  const locale = useLocale()
  const router = useRouter()
  const { data: session } = useSession()
  const setLang = useSetLanguage()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  if (!mounted) {
    return <div className="h-8 w-[52px] shrink-0" aria-hidden />
  }

  const next: 'zh' | 'en' = locale === 'zh' ? 'en' : 'zh'
  function choose() {
    setLocaleCookie(next) // 本设备即时生效层
    if (session) setLang.mutate(next) // 登录用户跨设备同步(未登录仅 cookie)
    router.refresh() // 服务端组件按新 cookie 重渲(URL 不变 · 无 redirect)
  }

  return (
    <button
      type="button"
      onClick={choose}
      aria-label={next === 'en' ? 'Switch to English' : '切换到中文'}
      title={next === 'en' ? 'English' : '中文'}
      className="flex h-8 shrink-0 items-center gap-1 rounded-md border border-paper bg-surface-subtle/40 px-2 text-muted-foreground transition-colors hover:border-midas-red/30 hover:text-foreground"
    >
      <Languages className="h-4 w-4" />
      <span className="text-xs font-medium">{locale === 'zh' ? 'EN' : '中'}</span>
    </button>
  )
}
