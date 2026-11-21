'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'

export function PublicLanguageLink({ english }: { english: boolean }) {
  const path = usePathname()
  const { setLocale } = useRuntimeLocale()
  const alternate = english ? path.replace(/^\/en(?=\/|$)/, '') || '/' : path === '/' ? '/en' : '/en' + path
  return (
    <Link href={alternate} hrefLang={english ? 'zh-CN' : 'en'}
      onClick={() => setLocale(english ? 'zh' : 'en')} className="hover:text-midas-red">
      {english ? '中文' : 'English'}
    </Link>
  )
}
