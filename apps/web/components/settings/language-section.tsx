'use client'

/**
 * 语言切换(i18n Phase 0 激活)· 设置页 section。
 *
 * 两档:中文 / English · 切换即时:next-intl router.replace(pathname, {locale}) 导航到对应 URL
 *   (as-needed:中文无前缀 `/` · 英文 `/en`)+ 自动写 NEXT_LOCALE cookie(本浏览器即时生效)。
 * ★与主题/涨跌色偏好不同:语言【登录后跨设备同步】—— 额外写回后端 language_pref(useSetLanguage)。
 * ★语言名(中文/English)恒以各自文字显示(t('zh')/t('en') 在中英两份 messages 里都是原文),
 *   方便用户不管当前界面语言都能找到自己的语言。
 */

import { useLocale, useTranslations } from 'next-intl'
import { useSession } from 'next-auth/react'

import { useSetLanguage } from '@/hooks/use-me'
import { usePathname, useRouter } from '@/i18n/navigation'
import { cn } from '@/lib/utils'

export function LanguageSection() {
  const t = useTranslations('settings.settings.language')
  const locale = useLocale()
  const router = useRouter()
  const pathname = usePathname()
  const { data: session } = useSession()
  const setLang = useSetLanguage()

  const OPTIONS: { value: 'zh' | 'en'; label: string; note: string }[] = [
    { value: 'zh', label: t('zh'), note: t('zh_note') },
    { value: 'en', label: t('en'), note: t('en_note') },
  ]

  function choose(next: 'zh' | 'en') {
    if (next === locale) return
    router.replace(pathname, { locale: next }) // 即时切 locale + next-intl 自动写 NEXT_LOCALE cookie
    if (session) setLang.mutate(next) // 登录用户跨设备同步(未登录仅 cookie)
  }

  return (
    <section className="mb-6 rounded-lg border border-paper bg-surface-card p-5">
      <h2 className="mb-1 font-serif text-lg font-bold text-foreground">{t('_')}</h2>
      <p className="mb-4 text-sm text-muted-foreground">{t('description')}</p>

      <div className="flex w-fit overflow-hidden rounded-lg border border-paper">
        {OPTIONS.map((o) => {
          const active = locale === o.value
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => choose(o.value)}
              aria-pressed={active}
              className={cn(
                'flex min-w-[120px] flex-col items-start gap-0.5 px-4 py-3 text-left transition-colors',
                active
                  ? 'bg-midas-red text-white'
                  : 'bg-background text-foreground hover:bg-midas-red-glow/40',
              )}
            >
              <span className="text-sm font-medium">{o.label}</span>
              <span
                className={cn('text-[11px]', active ? 'text-white/75' : 'text-muted-foreground/70')}
              >
                {o.note}
              </span>
            </button>
          )
        })}
      </div>

      <p className="mt-3 text-[11px] text-muted-foreground/60">{t('note')}</p>
    </section>
  )
}
