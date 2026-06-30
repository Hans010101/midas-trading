'use client'

/**
 * 选股筛选器页 · 股票第一批 功能1 · 1a MVP(只读 · 分析非建议)。
 *
 * 🔴 红线:结果是"符合条件的标的"客观列表 + 免责,非荐股;点击跳详情页(只读)。
 * 条件:价格 / 涨跌幅(spot 预筛)+ RSI 区间 / 均线多头排列(K线现算)· cn/us/hk 现货。
 */

import Link from 'next/link'
import { useState } from 'react'

import { useScreener } from '@/hooks/use-screener'
import type { ScreenerFilters, StockMarket } from '@/lib/api/screener'

const MARKETS: { key: StockMarket; label: string }[] = [
  { key: 'cn', label: 'A股' },
  { key: 'us', label: '美股' },
  { key: 'hk', label: '港股' },
]

const UP = '#DC143C' // 朱红(涨)· A股传统
const DOWN = '#0F6E5F' // 墨绿(跌)

function toNum(s: string): number | undefined {
  const v = Number(s)
  return s.trim() === '' || Number.isNaN(v) ? undefined : v
}

function NumInput({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
}) {
  return (
    <input
      type="number"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="w-24 rounded-md border border-paper bg-background px-2 py-1.5 text-sm"
    />
  )
}

export default function ScreenerPage() {
  const [market, setMarket] = useState<StockMarket>('cn')
  const [priceMin, setPriceMin] = useState('')
  const [priceMax, setPriceMax] = useState('')
  const [chgMin, setChgMin] = useState('')
  const [chgMax, setChgMax] = useState('')
  const [rsiMin, setRsiMin] = useState('')
  const [rsiMax, setRsiMax] = useState('')
  const [maBull, setMaBull] = useState(false)
  const [macdGolden, setMacdGolden] = useState(false)
  const [kdjGolden, setKdjGolden] = useState(false)
  const [bollBwMax, setBollBwMax] = useState('')
  const [volRatioMin, setVolRatioMin] = useState('')
  const screener = useScreener()

  function buildFilters(): ScreenerFilters {
    return {
      price_min: toNum(priceMin),
      price_max: toNum(priceMax),
      change_pct_min: toNum(chgMin),
      change_pct_max: toNum(chgMax),
      rsi_min: toNum(rsiMin),
      rsi_max: toNum(rsiMax),
      ma_bull_aligned: maBull ? true : undefined,
      macd_golden_cross: macdGolden ? true : undefined,
      kdj_golden_cross: kdjGolden ? true : undefined,
      boll_bandwidth_max: toNum(bollBwMax),
      volume_ratio_min: toNum(volRatioMin),
    }
  }

  function onSubmit() {
    const filters = buildFilters()
    const empty = Object.values(filters).every((v) => v === undefined)
    if (empty) {
      return
    }
    screener.mutate({ market, filters })
  }

  const resp = screener.data
  const hasTechResult =
    resp?.hits.some((h) => h.rsi_14 !== null || h.ma_5 !== null) ?? false

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-2 font-serif text-2xl font-bold text-foreground">选股筛选器</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        按价格 / 涨跌幅 / RSI / 均线排列,筛选符合条件的标的(A股 / 美股 / 港股现货 · 仅供参考)。
      </p>

      {/* 市场切换 */}
      <div className="mb-4 flex gap-2">
        {MARKETS.map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() => setMarket(m.key)}
            className={`rounded-md px-4 py-1.5 text-sm transition-colors ${
              market === m.key
                ? 'bg-midas-red text-white'
                : 'border border-paper bg-cream text-foreground hover:bg-paper/40'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* 条件表单 */}
      <div className="mb-4 space-y-3 rounded-lg border border-paper bg-cream p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-20 text-sm text-foreground">现价</span>
          <NumInput value={priceMin} onChange={setPriceMin} placeholder="最低" />
          <span className="text-muted-foreground">~</span>
          <NumInput value={priceMax} onChange={setPriceMax} placeholder="最高" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-20 text-sm text-foreground">涨跌幅 %</span>
          <NumInput value={chgMin} onChange={setChgMin} placeholder="最低" />
          <span className="text-muted-foreground">~</span>
          <NumInput value={chgMax} onChange={setChgMax} placeholder="最高" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-20 text-sm text-foreground">RSI(14)</span>
          <NumInput value={rsiMin} onChange={setRsiMin} placeholder="0" />
          <span className="text-muted-foreground">~</span>
          <NumInput value={rsiMax} onChange={setRsiMax} placeholder="100" />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            checked={maBull}
            onChange={(e) => setMaBull(e.target.checked)}
            className="h-4 w-4 accent-midas-red"
          />
          均线多头排列(MA5 &gt; MA20 &gt; MA60)
        </label>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={macdGolden}
              onChange={(e) => setMacdGolden(e.target.checked)}
              className="h-4 w-4 accent-midas-red"
            />
            MACD 金叉
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={kdjGolden}
              onChange={(e) => setKdjGolden(e.target.checked)}
              className="h-4 w-4 accent-midas-red"
            />
            KDJ 金叉
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-20 text-sm text-foreground">布林带宽</span>
          <span className="text-sm text-muted-foreground">≤</span>
          <NumInput value={bollBwMax} onChange={setBollBwMax} placeholder="如 10" />
          <span className="text-sm text-muted-foreground">%(收窄)</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-20 text-sm text-foreground">量比</span>
          <span className="text-sm text-muted-foreground">≥</span>
          <NumInput value={volRatioMin} onChange={setVolRatioMin} placeholder="如 1.5" />
        </div>
        <button
          type="button"
          onClick={onSubmit}
          disabled={screener.isPending}
          className="rounded-md bg-midas-red px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:opacity-50"
        >
          {screener.isPending ? '筛选中…' : '筛选'}
        </button>
      </div>

      {/* 结果 */}
      {screener.isError && (
        <p className="text-sm text-midas-red">筛选失败,请稍后重试。</p>
      )}
      {resp && (
        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="font-serif text-lg font-bold text-foreground">
              符合条件的标的({resp.total})
            </h2>
            <span className="text-xs text-muted-foreground">扫描 {resp.scanned} 只</span>
          </div>
          {resp.candidate_capped && (
            <p className="mb-2 rounded-md border border-gold/40 bg-gold/[0.06] px-3 py-2 text-xs text-muted-foreground">
              技术指标筛选覆盖成交最活跃的部分标的(港股仅主要成分股有 K线深度)· 结果可能未含全市场。
            </p>
          )}
          {resp.hits.length === 0 && (
            <p className="text-sm text-muted-foreground/70">没有符合条件的标的,试试放宽条件。</p>
          )}
          <ul className="space-y-1.5">
            {resp.hits.map((h) => {
              const up = h.change_pct >= 0
              return (
                <li key={h.symbol}>
                  <Link
                    href={`/${market}-preview?symbol=${encodeURIComponent(h.symbol)}&name=${encodeURIComponent(h.name)}`}
                    className="flex items-center justify-between gap-2 rounded-md border border-paper bg-cream px-3 py-2 transition-colors hover:border-midas-red/40"
                  >
                    <span className="text-sm text-foreground">
                      <span className="font-mono">{h.symbol}</span> · {h.name}
                    </span>
                    <span className="flex items-center gap-3 font-mono text-sm">
                      <span className="text-foreground">{h.last_price.toFixed(2)}</span>
                      <span style={{ color: up ? UP : DOWN }}>
                        {up ? '+' : ''}
                        {h.change_pct.toFixed(2)}%
                      </span>
                      {h.rsi_14 !== null && (
                        <span className="text-muted-foreground">RSI {h.rsi_14.toFixed(0)}</span>
                      )}
                      {h.volume_ratio !== null && (
                        <span className="text-muted-foreground">量比 {h.volume_ratio.toFixed(1)}</span>
                      )}
                      {(h.macd_golden === true || h.kdj_golden === true) && (
                        <span style={{ color: UP }}>金叉</span>
                      )}
                    </span>
                  </Link>
                </li>
              )
            })}
          </ul>
          {(hasTechResult || resp.hits.length > 0) && (
            <p className="mt-4 text-xs text-muted-foreground/70">{resp.disclaimer}</p>
          )}
        </div>
      )}
    </div>
  )
}
