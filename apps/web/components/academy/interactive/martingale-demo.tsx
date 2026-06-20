'use client'

import { useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { betAtStreak, cumulativeStake } from './martingale.calc'

const BASE = 2
const CAP = 100
const VMAX = 130
const TOP = 14
const BOT = 156
const L = 30
const R = 500
const vy = (v: number) => BOT - (Math.min(v, VMAX) / VMAX) * (BOT - TOP)

export function MartingaleDemo() {
  const [streak, setStreak] = useState(3)
  const bet = betAtStreak(BASE, streak)
  const cum = cumulativeStake(BASE, streak)
  const bust = cum > CAP
  const bars = Array.from({ length: streak + 1 }, (_, i) => betAtStreak(BASE, i))
  const bw = (R - L) / 8

  return (
    <InteractiveCard
      title="马丁格尔(反面演示)"
      subtitle="亏损后加倍下注,下注额指数膨胀。拖连亏次数,看累计投入冲破本金、爆仓归零。"
    >
      <div className="mb-3.5 rounded border border-midas-red/40 bg-midas-red/10 px-3.5 py-2.5">
        <span className="text-sm font-semibold leading-relaxed text-midas-red-deep">反面演示 —— 有限资金下必然爆仓。马丁格尔是风险警示,不可用、绝非可用策略,不存在「能回本/能稳赚」。</span>
      </div>
      <div className="mb-3 flex items-center gap-3">
        <span className="shrink-0 text-sm text-foreground/60">连亏次数</span>
        <input type="range" min={0} max={7} step={1} value={streak} onChange={(e) => setStreak(Number(e.target.value))} className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="连亏次数" />
        <span className="w-6 shrink-0 text-right font-tabular text-sm font-semibold">{streak}</span>
      </div>
      <svg viewBox="0 0 520 180" className="h-auto w-full select-none" role="img" aria-label="每次下注额的指数膨胀柱状与本金线">
        <line x1={L} y1={vy(CAP)} x2={R} y2={vy(CAP)} className="stroke-midas-red" strokeWidth={1.3} strokeDasharray="4 3" />
        <text x={R} y={vy(CAP) - 4} textAnchor="end" className="fill-midas-red font-tabular text-[11px]">本金 100</text>
        {bars.map((b, i) => {
          const x = L + i * bw + bw * 0.18
          const w = bw * 0.64
          const overflow = b > VMAX
          return (
            <g key={i}>
              <rect x={x} y={vy(b).toFixed(1)} width={w.toFixed(1)} height={(BOT - vy(b)).toFixed(1)} rx={2} className="fill-midas-red" fillOpacity={Number((0.35 + i * 0.09).toFixed(2))} />
              {overflow ? (
                <text x={x + w / 2} y={TOP + 8} textAnchor="middle" className="fill-midas-red font-tabular text-[10px]">↑{b}</text>
              ) : (
                <text x={x + w / 2} y={vy(b) - 3} textAnchor="middle" className="fill-foreground/60 font-tabular text-[10px]">{b}</text>
              )}
            </g>
          )
        })}
      </svg>
      <div className="my-3 grid grid-cols-3 gap-3">
        <div className="rounded-md bg-surface-subtle p-3.5">
          <div className="text-[13px] text-foreground/60">本次下注</div>
          <div className="font-tabular text-xl font-semibold">{bet}</div>
        </div>
        <div className="rounded-md bg-surface-subtle p-3.5">
          <div className="text-[13px] text-foreground/60">累计投入</div>
          <div className={'font-tabular text-xl font-semibold ' + (bust ? 'text-midas-red' : '')}>{cum}</div>
        </div>
        <div className="rounded-md bg-surface-subtle p-3.5">
          <div className="text-[13px] text-foreground/60">本金</div>
          <div className="font-tabular text-xl font-semibold">100</div>
        </div>
      </div>
      <div className={'rounded px-3 py-2 text-sm ' + (bust ? 'bg-midas-red/10 text-midas-red' : 'bg-surface-subtle text-foreground/70')}>
        {bust
          ? <><strong className="font-semibold">爆仓归零</strong>:连亏 {streak} 次,累计投入 {cum} 已超过本金 100 — 第 {streak} 次的 {bet} 注无法补足,本金耗尽。这是必然结局。</>
          : <>连亏 {streak} 次:本次需下注 {bet},累计投入 {cum}(本金 100 还撑得住)。但注额每次翻倍,再亏几次就崩 — 拖到底看。</>}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        下注额 = 基注 × 2ⁿ(<strong className="text-foreground/80">指数膨胀</strong>),累计投入 = 基注 ×(2ⁿ⁺¹−1)。本金有限,连亏到某次累计必然超过本金 → <strong className="text-midas-red">爆仓归零</strong>。这是马丁格尔的数学宿命,不是「还没回本」。
      </p>
    </InteractiveCard>
  )
}
