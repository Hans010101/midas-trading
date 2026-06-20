'use client'

import { useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { cumulativeCost, fundingPayer, payerAmount } from './funding-rate.calc'

const NOTIONAL = 10000

export function FundingRateDemo() {
  const [rate, setRate] = useState(0.0001) // 0.01%
  const [settlements, setSettlements] = useState(3)

  const payer = fundingPayer(rate)
  const once = payerAmount(NOTIONAL, rate)
  const total = cumulativeCost(NOTIONAL, rate, settlements)
  const pct = (rate * 100).toFixed(2)

  const longPays = payer === 'long'
  const shortPays = payer === 'short'

  return (
    <InteractiveCard
      title="资金费率:谁付谁"
      subtitle={`名义仓位固定 ${NOTIONAL.toLocaleString()}。拖动费率正负,看资金费在多空之间怎么收付。`}
    >
      <label className="mb-4 flex items-center gap-3 text-sm">
        <span className="shrink-0 text-foreground/60">费率</span>
        <input
          type="range"
          min={-0.001}
          max={0.001}
          step={0.0001}
          value={rate}
          onChange={(e) => setRate(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-midas-red"
          aria-label="资金费率"
        />
        <span className="w-16 shrink-0 text-right font-tabular font-semibold text-midas-red">{pct}%</span>
      </label>

      <div className="flex items-stretch gap-2">
        <div
          className={
            'flex-1 rounded border px-3 py-3 text-center ' +
            (longPays ? 'border-midas-red/30 bg-midas-red/5' : 'border-paper bg-surface-subtle/40')
          }
        >
          <div className="text-sm font-medium text-foreground/85">多头</div>
          <div className={'mt-1 text-xs ' + (longPays ? 'text-midas-red' : 'text-success')}>
            {payer === 'none' ? '—' : longPays ? `付出 ${once.toFixed(2)}` : `收取 ${once.toFixed(2)}`}
          </div>
        </div>
        <div className="flex w-16 flex-col items-center justify-center">
          <div className="font-tabular text-lg text-foreground/70">
            {payer === 'none' ? '＝' : longPays ? '→' : '←'}
          </div>
          <div className="text-[10px] text-foreground/55">每8h</div>
        </div>
        <div
          className={
            'flex-1 rounded border px-3 py-3 text-center ' +
            (shortPays ? 'border-midas-red/30 bg-midas-red/5' : 'border-paper bg-surface-subtle/40')
          }
        >
          <div className="text-sm font-medium text-foreground/85">空头</div>
          <div className={'mt-1 text-xs ' + (shortPays ? 'text-midas-red' : 'text-success')}>
            {payer === 'none' ? '—' : shortPays ? `付出 ${once.toFixed(2)}` : `收取 ${once.toFixed(2)}`}
          </div>
        </div>
      </div>

      <div
        className={
          'mt-3 rounded px-3 py-2 text-sm font-medium ' +
          (payer === 'none' ? 'bg-surface-subtle text-foreground/70' : 'bg-success/10 text-success')
        }
      >
        {payer === 'none'
          ? '费率为 0:本次无人收付。'
          : `${longPays ? '正费率 → 多头付空头' : '负费率 → 空头付多头'}(单次 ${once.toFixed(2)})`}
      </div>

      <label className="mt-3 flex items-center gap-3 text-sm">
        <span className="shrink-0 text-foreground/60">持有</span>
        <input
          type="range"
          min={1}
          max={30}
          step={1}
          value={settlements}
          onChange={(e) => setSettlements(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-midas-red"
          aria-label="结算次数"
        />
        <span className="w-20 shrink-0 text-right font-tabular text-foreground/70">{settlements} 次结算</span>
      </label>
      <p className="mt-2 text-sm text-foreground/85">
        持有 {settlements} 次结算({(settlements * 8)} 小时)累计{payer === 'none' ? '收付' : '持有成本'}{' '}
        <span className="font-tabular font-semibold text-midas-red">{total.toFixed(2)}</span>。
      </p>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        资金费是<strong className="text-foreground/80">多空之间</strong>的收付,不是平台手续费;长期持仓会按结算次数累计成本。
      </p>
    </InteractiveCard>
  )
}
