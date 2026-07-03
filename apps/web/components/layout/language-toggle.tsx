'use client'

/**
 * 顶栏语言快捷切换(i18n Phase 0 激活)· 中↔EN 一键切。
 *
 * 显示【要切到的目标语言】(中文界面显 EN · 英文界面显 中)· 点击 router.replace 导航到对应
 *   locale URL(as-needed:中文 `/` 无前缀 · 英文 `/en`)+ next-intl 自动写 NEXT_LOCALE cookie。
 * ★访客(未登录)也能切(纯 cookie + 导航)· 登录用户额外写回后端 language_pref 跨设备同步。
 * ★挂载前渲染占位,避免 SSR/首帧布局跳动。
 */

import { Languages } from 'lucide-react'
import { useLocale } from 'next-intl'
import { useSession } from 'next-auth/react'
import { useEffect, useState } from 'react'

import { useSetLanguage } from '@/hooks/use-me'
import { usePathname, useRouter } from '@/i18n/navigation'

export function LanguageToggle() {
  const locale = useLocale()
  const router = useRouter()
  const pathname = usePathname()
  const { data: session } = useSession()
  const setLang = useSetLanguage()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  if (!mounted) {
    return <div className="h-8 w-[52px] shrink-0" aria-hidden />
  }

  const next: 'zh' | 'en' = locale === 'zh' ? 'en' : 'zh'
  function choose() {
    router.replace(pathname, { locale: next })
    if (session) setLang.mutate(next)
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
