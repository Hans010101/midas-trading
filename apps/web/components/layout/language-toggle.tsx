'use client'

/**
 * 顶栏语言切换(i18n 激活 · cookie 模式)· 中↔EN 一键切。
 *
 * 机制:写 NEXT_LOCALE cookie → router.refresh() 让服务端按新 cookie 重渲染(★URL 不变 ·
 *   无 [locale] 路由 · 结构性避开历史 redirect loop)。登录用户额外 PATCH /user/language 落库
 *   (resolve_lang 扩回 ② 据此持久 + 跨设备 · best-effort 失败不阻塞切换)。
 * ★locale 由 NextIntlClientProvider 从 cookie 注入,SSR/CSR 一致 → 无需 mounted 占位(与 ThemeToggle 不同)。
 */
import { useSession } from 'next-auth/react'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { setLanguage } from '@/lib/api/me'

export function LanguageToggle() {
  const { locale, setLocale } = useRuntimeLocale()
  const { data: session } = useSession()

  const isEn = locale === 'en'
  const next = isEn ? 'zh' : 'en'

  function switchLang() {
    setLocale(next)
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
