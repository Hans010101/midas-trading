'use client'

/**
 * 加密频道 · 列表页(币种列表 / 涨幅榜)· 静态布局骨架。
 *
 * ⚠ 这是【布局骨架】· 不接真实数据:
 *   · 所有指标卡数值 / 表格行 = 占位示意值
 *   · Tab(合约/现货)可点切换(本地 state)· 但两边都用同一份示意数据
 *   · 搜索框 / 刷新按钮 = 纯视觉,不触发任何请求
 *   · 行可点击的视觉(hover 高亮 + cursor + 右侧 ›)= 示意「点行进详情页」,
 *     真正跳转(→ /crypto-preview 详情页)是下一步的事,本步不接
 *
 * 两层结构:本页(列表)→ 点某币 → /crypto-preview(已有详情页)。
 * 路由怎么挂进「加密」频道导航是下一步,本步纯新增页面,不碰现有页面/路由。
 *
 * 视觉:点金视觉系统 · 帝王金主色 · 涨红(bull #DC143C)/ 跌绿(bear #0F6E5F)·
 *       多空占比小色条沿用详情页 6 维度图的 多=青绿 / 空=浅红。
 * 预览:本地 pnpm dev → /crypto-market
 */

import { useState } from 'react'

import { cn } from '@/lib/utils'

// ── 占位示意数据(纯静态 · 非真实)──────────────────────────────────────────
interface Row {
  symbol: string
  price: string
  chgPct: number // 24H 涨跌 %(正涨负跌)
  high: string
  low: string
  funding: number // 资金费率 %(正/负)
  longPct: number // 账户多空比 · 多方占比 0..100
  ratio: string // 多空比值文本
  oiChg: number // OI 24H 变化 %
  turnover: string // 24H 成交额
}

const SAMPLE_ROWS: Row[] = [
  { symbol: 'BTC/USDT', price: '64,820.5', chgPct: 2.34, high: '65,400.0', low: '62,980.0', funding: 0.01, longPct: 64, ratio: '1.85', oiChg: 8.2, turnover: '12.4B' },
  { symbol: 'ETH/USDT', price: '3,142.8', chgPct: 3.91, high: '3,180.0', low: '2,990.0', funding: 0.015, longPct: 61, ratio: '1.56', oiChg: 5.7, turnover: '6.8B' },
  { symbol: 'SOL/USDT', price: '148.32', chgPct: 6.12, high: '151.0', low: '138.5', funding: 0.022, longPct: 68, ratio: '2.13', oiChg: 14.3, turnover: '2.1B' },
  { symbol: 'BNB/USDT', price: '592.40', chgPct: 1.08, high: '598.0', low: '585.0', funding: 0.008, longPct: 55, ratio: '1.22', oiChg: 2.1, turnover: '980M' },
  { symbol: 'XRP/USDT', price: '0.5218', chgPct: -1.74, high: '0.5390', low: '0.5180', funding: -0.005, longPct: 47, ratio: '0.89', oiChg: -3.4, turnover: '720M' },
  { symbol: 'DOGE/USDT', price: '0.1402', chgPct: 4.55, high: '0.1440', low: '0.1320', funding: 0.018, longPct: 66, ratio: '1.94', oiChg: 9.8, turnover: '510M' },
  { symbol: 'ADA/USDT', price: '0.4471', chgPct: -2.30, high: '0.4620', low: '0.4450', funding: -0.003, longPct: 44, ratio: '0.79', oiChg: -1.2, turnover: '430M' },
  { symbol: 'AVAX/USDT', price: '28.74', chgPct: 5.03, high: '29.2', low: '27.1', funding: 0.012, longPct: 63, ratio: '1.70', oiChg: 7.1, turnover: '360M' },
  { symbol: 'LINK/USDT', price: '14.06', chgPct: 0.42, high: '14.3', low: '13.8', funding: 0.006, longPct: 52, ratio: '1.08', oiChg: 0.6, turnover: '280M' },
  { symbol: 'TON/USDT', price: '6.812', chgPct: -3.18, high: '7.05', low: '6.78', funding: -0.009, longPct: 41, ratio: '0.70', oiChg: -5.6, turnover: '210M' },
  { symbol: 'TRX/USDT', price: '0.1186', chgPct: 0.95, high: '0.1198', low: '0.1170', funding: 0.004, longPct: 53, ratio: '1.13', oiChg: 1.4, turnover: '180M' },
  { symbol: 'LTC/USDT', price: '84.23', chgPct: -0.61, high: '85.6', low: '83.2', funding: -0.002, longPct: 49, ratio: '0.96', oiChg: -0.8, turnover: '150M' },
]

const METRICS = [
  { label: '24H 合约总成交额', value: '$48.6B', sub: '示意' },
  { label: '恐慌贪婪指数', value: '72', sub: '贪婪 · 示意', tone: 'bull' as const },
  { label: 'BTC 价格', value: '$64,820', sub: '+2.34%', tone: 'bull' as const },
  { label: 'ETH 价格', value: '$3,142', sub: '+3.91%', tone: 'bull' as const },
]

export default function CryptoMarketPage() {
  const [tab, setTab] = useState<'perp' | 'spot'>('perp')

  return (
    <main className="min-h-screen bg-background text-foreground">
      {/* 顶部说明条:骨架标识 */}
      <div className="border-b border-dashed border-gold/60 bg-gold/10 px-6 py-2 text-center text-xs text-gold">
        加密市场 · 列表页布局骨架 · 数值为示意 · 不接真实数据 · 点行进详情页(跳转下一步接)
      </div>

      <div className="mx-auto max-w-[1600px] px-6 py-5">
        {/* 标题 */}
        <div className="mb-4 flex items-baseline gap-3">
          <h1 className="font-serif text-2xl font-bold text-midas-red">加密市场</h1>
          <span className="text-sm text-muted-foreground">合约 / 现货 · 24H 行情榜</span>
        </div>

        {/* 1 · 顶部 4 指标卡 */}
        <div className="mb-5 grid grid-cols-2 gap-4 md:grid-cols-4">
          {METRICS.map((m) => (
            <div key={m.label} className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
              <div className="text-xs text-muted-foreground">{m.label}</div>
              <div
                className={cn(
                  'mt-1 font-mono text-2xl font-bold',
                  m.tone === 'bull' ? 'text-bull' : 'text-foreground',
                )}
              >
                {m.value}
              </div>
              <div className={cn('mt-0.5 text-[11px]', m.tone === 'bull' ? 'text-bull' : 'text-muted-foreground/70')}>
                {m.sub}
              </div>
            </div>
          ))}
        </div>

        {/* 2/3 · 工具条:Tab 切换 + 搜索 + 刷新 */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex overflow-hidden rounded-md border border-paper text-sm">
            <button
              type="button"
              onClick={() => setTab('perp')}
              className={cn('px-4 py-1.5 transition-colors', tab === 'perp' ? 'bg-midas-red text-white' : 'text-muted-foreground hover:bg-midas-red-glow/50')}
            >
              合约 24H 涨幅榜
            </button>
            <button
              type="button"
              onClick={() => setTab('spot')}
              className={cn('px-4 py-1.5 transition-colors', tab === 'spot' ? 'bg-midas-red text-white' : 'text-muted-foreground hover:bg-midas-red-glow/50')}
            >
              现货 24H 涨幅榜
            </button>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-md border border-paper bg-cream/40 px-3 py-1.5 text-sm">
              <SearchIcon />
              <input
                type="text"
                placeholder="搜索交易对(如 BTC)"
                className="w-44 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
              />
            </div>
            <button
              type="button"
              className="flex items-center gap-1.5 rounded-md border border-paper px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-midas-red hover:text-midas-red"
              title="刷新(示意)"
            >
              <RefreshIcon />
              刷新
            </button>
          </div>
        </div>

        {/* 4/5 · 币种列表表格 */}
        <div className="overflow-x-auto rounded-lg border border-paper">
          <table className="w-full min-w-[1100px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-paper bg-cream/50 text-xs text-muted-foreground">
                <Th className="w-12 text-center">#</Th>
                <Th className="text-left">交易对</Th>
                <Th>最新价格</Th>
                <Th>24H 涨跌%</Th>
                <Th>24H 最高</Th>
                <Th>24H 最低</Th>
                <Th>资金费率</Th>
                <Th className="text-center">账户多空比</Th>
                <Th>OI 24H 变化</Th>
                <Th>24H 成交额</Th>
                <Th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {SAMPLE_ROWS.map((r, i) => (
                <tr
                  key={r.symbol}
                  className="group cursor-pointer border-b border-paper/60 transition-colors hover:bg-midas-red-glow/30"
                  title="点击进入详情页(跳转下一步接)"
                >
                  <td className="px-3 py-2.5 text-center font-mono text-xs text-muted-foreground/70">{i + 1}</td>
                  <td className="px-3 py-2.5">
                    <span className="font-serif font-bold text-foreground">{r.symbol}</span>
                  </td>
                  <Td>{r.price}</Td>
                  <Td className={r.chgPct >= 0 ? 'text-bull' : 'text-bear'}>
                    {r.chgPct >= 0 ? '+' : ''}{r.chgPct.toFixed(2)}%
                  </Td>
                  <Td className="text-muted-foreground/80">{r.high}</Td>
                  <Td className="text-muted-foreground/80">{r.low}</Td>
                  <Td className={r.funding >= 0 ? 'text-bull' : 'text-bear'}>
                    {r.funding >= 0 ? '+' : ''}{r.funding.toFixed(3)}%
                  </Td>
                  <td className="px-3 py-2.5">
                    <LongShortBar longPct={r.longPct} ratio={r.ratio} />
                  </td>
                  <Td className={r.oiChg >= 0 ? 'text-bull' : 'text-bear'}>
                    {r.oiChg >= 0 ? '+' : ''}{r.oiChg.toFixed(1)}%
                  </Td>
                  <Td className="text-muted-foreground/80">{r.turnover}</Td>
                  <td className="px-2 text-center text-muted-foreground/30 transition-colors group-hover:text-midas-red">›</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-3 text-[11px] text-muted-foreground/60">
          数据为示意占位 · 接真实行情(/api/v1/crypto/*)+ 点行跳转详情页为下一步 · 仅供参考,不构成投资建议
        </p>
      </div>
    </main>
  )
}

// ── 多空占比小色条 · 多=青绿 / 空=浅红(沿用详情页 6 维度图配色)──────────────
function LongShortBar({ longPct, ratio }: { longPct: number; ratio: string }) {
  const shortPct = 100 - longPct
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-2 w-16 overflow-hidden rounded-full bg-paper">
        <div style={{ width: `${longPct}%`, backgroundColor: '#1FA383' }} />
        <div style={{ width: `${shortPct}%`, backgroundColor: '#E8918C' }} />
      </div>
      <span className="font-mono text-xs tabular-nums text-foreground/80">{ratio}</span>
    </div>
  )
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={cn('px-3 py-2 text-right font-medium', className)}>{children}</th>
}
function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn('px-3 py-2.5 text-right font-mono tabular-nums', className)}>{children}</td>
}

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted-foreground/50">
      <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
    </svg>
  )
}
function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v5h-5" />
    </svg>
  )
}
