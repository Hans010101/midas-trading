'use client'

import { usePathname, useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { setLanguage } from '@/lib/api/me'

export function LanguageToggle() {
  const { locale, setLocale } = useRuntimeLocale()
  const { data: session } = useSession()
  const pathname = usePathname()
  const router = useRouter()
  const isEn = locale === 'en'
  const next = isEn ? 'zh' : 'en'

  function switchLang() {
    setLocale(next)
    if (pathname === '/news' || pathname === '/en/news') {
      router.push((next === 'en' ? '/en/news' : '/news') + window.location.search, { scroll: false })
    }
    const token = session?.accessToken ?? ''
    // 登录用户落库跨设备(best-effort · guest 或失败都不影响 cookie 已切)
    if (token) void setLanguage(token, next).catch(() => undefined)
  }

  return (
    <button
      type="button"
      onClick={switchLang}
      aria-label={isEn ? 'Switch to Chinese / 切换到中文' : '切换到英文 / Switch to English'}
      aria-pressed={isEn}
      title={isEn ? '中文' : 'English'}
      className="flex h-8 min-w-8 shrink-0 items-center justify-center rounded-md border border-paper bg-surface-subtle/40 px-2 font-mono text-xs font-semibold text-muted-foreground transition-colors hover:border-midas-red/30 hover:text-foreground"
    >
      {isEn ? '中' : 'EN'}
    </button>
  )
}
