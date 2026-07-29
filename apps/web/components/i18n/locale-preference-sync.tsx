'use client'

import { useEffect } from 'react'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { useMe } from '@/hooks/use-me'
import { hasLocaleCookie } from '@/lib/i18n/locale-cookie'

export function LocalePreferenceSync() {
  const { setLocale } = useRuntimeLocale()
  const { data: me } = useMe()

  // A device with an explicit cookie always wins. On a new device, hydrate the
  // language previously saved to the signed-in account.
  useEffect(() => {
    const preference = me?.language_pref
    if (
      !hasLocaleCookie() &&
      (preference === 'zh' || preference === 'en')
    ) {
      setLocale(preference)
    }
  }, [me?.language_pref, setLocale])

  return null
}
