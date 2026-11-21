import Link from 'next/link'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { DETAIL_SYMBOLS, detailHref, type DetailMarket } from '@/lib/seo/detail-symbols'

export function MarketHeading({ market, title }: { market: DetailMarket; title: string }) {
  const { locale } = useRuntimeLocale()
  return (
    <div className="mb-3 flex flex-wrap items-baseline gap-x-5 gap-y-1">
      <h1 className="font-serif text-lg font-bold">{title}</h1>
      <nav aria-label={locale === 'en' ? 'Instrument details' : '品种详情'} className="flex flex-wrap gap-x-4 text-xs text-muted-foreground">
        {DETAIL_SYMBOLS[market].slice(0, 4).map(({ symbol, name }) => (
          <Link key={symbol} href={detailHref({ market, symbol })} prefetch={false} className="hover:text-midas-red hover:underline">
            {locale === 'zh' && (market === 'hk' || market === 'cn') ? name + ' ' : ''}{symbol}
          </Link>
        ))}
      </nav>
    </div>
  )
}
