/**
 * 详情页 SEO 语义壳(SEO 批7 · server 静态 · 作为路径段路由的 Suspense fallback)。
 *
 * 作用:路径段页 `/{market}/[symbol]` 的 client 详情组件(useSearchParams bailout)在
 * Suspense 内 → 爬虫(无 JS)看到的 SSR HTML = 本 fallback。页面 generateStaticParams +
 * dynamicParams=false = 纯静态 → 本壳在 build 期烤进静态 HTML(零 per-request SSR)。
 * 用户端 client 详情组件 hydrate 后替换本壳。
 *
 * ★红线(硬约束③):纯功能骨架 · 无 bias/方向/涨跌预测/具体价格/买卖词 · 底部固定免责。
 *   bias(偏多/偏空/中性)是 live 数据 → 只在 client 详情里出现,不进本静态壳。
 */

import { TopNav } from '@/components/layout/top-nav'
import type { DetailMarket } from '@/lib/seo/detail-symbols'

const MARKET_LABEL: Record<DetailMarket, string> = {
  crypto: '加密货币',
  cn: 'A股',
  us: '美股',
  hk: '港股',
}

export function DetailSeoShell({
  market,
  symbol,
  name,
}: {
  market: DetailMarket
  symbol: string
  name: string
}) {
  const label = MARKET_LABEL[market]
  return (
    <main className="min-h-screen bg-background text-foreground">
      <TopNav />
      <div className="mx-auto max-w-[1600px] px-6 py-8">
        <h1 className="font-serif text-2xl font-bold text-foreground">
          {name}（{symbol}）· {label}行情与技术分析
        </h1>
        <p className="mt-4 max-w-3xl leading-[1.85] text-foreground/85">
          {name}（{symbol}）的多周期 K 线图、技术指标（均线 / MACD / RSI / 布林带）与技术面客观结构诊断，
          配虚拟交易沙盘（全程虚拟资金）。
          {market === 'crypto' &&
            '并含永续合约资金费率、持仓量、多空比等合约数据。'}
        </p>
        <p className="mt-3 max-w-3xl leading-[1.85] text-muted-foreground">
          点金 Midas 提供 {label} {name} 的行情走势与结构化技术分析，帮助你客观理解价格结构。
          数据实时加载中……
        </p>
        <p className="mt-6 text-sm text-muted-foreground/70">
          ⚠ 本页为 K 线结构与技术数据的客观展示，仅供参考，不构成任何投资建议。所有交易均为虚拟资金模拟。
        </p>
      </div>
    </main>
  )
}
