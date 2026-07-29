'use client'

import { useTranslations } from 'next-intl'
import { useSession } from 'next-auth/react'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import type { Locale } from '@/i18n/routing'
import { setLanguage } from '@/lib/api/me'
import { cn } from '@/lib/utils'

export function LanguageSection() {
  const t = useTranslations('runtime.language')
  const { locale, setLocale } = useRuntimeLocale()
  const { data: session } = useSession()

  const options: ReadonlyArray<{
    value: Locale
    label: string
    note: string
  }> = [
    { value: 'zh', label: '中文', note: t('zhNote') },
    { value: 'en', label: 'English', note: t('enNote') },
  ]

  function choose(next: Locale) {
    if (next === locale) return
    setLocale(next)
    const token = session?.accessToken ?? ''
    if (token) void setLanguage(token, next).catch(() => undefined)
  }

  return (
    <section className="mb-6 rounded-lg border border-paper bg-surface-card p-5">
      <h2 className="mb-1 font-serif text-lg font-bold text-foreground">
        {t('title')}
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">{t('description')}</p>

      <div className="flex w-fit overflow-hidden rounded-lg border border-paper">
        {options.map((option) => {
          const active = locale === option.value
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => choose(option.value)}
              aria-pressed={active}
              className={cn(
                'flex min-w-[132px] flex-col items-start gap-0.5 px-4 py-3 text-left transition-colors',
                active
                  ? 'bg-midas-red text-white'
                  : 'bg-background text-foreground hover:bg-midas-red-glow/40',
              )}
            >
              <span className="text-sm font-medium">{option.label}</span>
              <span
                className={cn(
                  'text-[11px]',
                  active ? 'text-white/75' : 'text-muted-foreground/70',
                )}
              >
                {option.note}
              </span>
            </button>
          )
        })}
      </div>

      <p className="mt-3 text-[11px] text-muted-foreground/60">{t('note')}</p>
    </section>
  )
}
