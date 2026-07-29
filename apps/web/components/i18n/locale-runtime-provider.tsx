'use client'

import { NextIntlClientProvider } from 'next-intl'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

import type { Locale } from '@/i18n/routing'
import { getLocaleCookie, setLocaleCookie } from '@/lib/i18n/locale-cookie'
import enMessages from '@/messages/en.json'
import zhMessages from '@/messages/zh.json'

import { CatalogTranslationBridge } from './catalog-translation-bridge'

type LocaleRuntime = Readonly<{
  locale: Locale
  setLocale: (locale: Locale) => void
}>

const LocaleRuntimeContext = createContext<LocaleRuntime | null>(null)

function applyDocumentLocale(locale: Locale): void {
  document.documentElement.lang = locale === 'en' ? 'en' : 'zh-CN'
  document.documentElement.dataset.locale = locale
}

export function LocaleRuntimeProvider({
  initialLocale,
  children,
}: {
  initialLocale: Locale
  children: React.ReactNode
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale)

  const setLocale = useCallback((next: Locale) => {
    setLocaleCookie(next)
    setLocaleState(next)
    applyDocumentLocale(next)
  }, [])

  // Static routes are built in Chinese. On hydration, honor the persisted cookie
  // so reloads keep the selected language without forcing every page dynamic.
  useEffect(() => {
    const persisted = getLocaleCookie()
    if (persisted !== locale) {
      setLocaleState(persisted)
    }
    applyDocumentLocale(persisted)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    applyDocumentLocale(locale)
  }, [locale])

  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale])
  const messages = locale === 'en' ? enMessages : zhMessages

  return (
    <LocaleRuntimeContext.Provider value={value}>
      <NextIntlClientProvider locale={locale} messages={messages}>
        {children}
        <CatalogTranslationBridge />
      </NextIntlClientProvider>
    </LocaleRuntimeContext.Provider>
  )
}

export function useRuntimeLocale(): LocaleRuntime {
  const value = useContext(LocaleRuntimeContext)
  if (!value) {
    throw new Error('useRuntimeLocale must be used within LocaleRuntimeProvider')
  }
  return value
}
