'use client'

import { useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { riskRewardRatio, expectancy, breakEvenWinRate } from './risk-reward.calc'

function Slider({ label, value, min, max, onChange, suffix }: { label: string; value: number; min: number; max: number; onChange: (v: number) => void; suffix?: string }) {
  return (
    <div className="mb-2.5 flex items-center gap-3">
      <span className="w-[72px] shrink-0 text-sm text-foreground/60">{label}</span>
      <input type="range" min={min} max={max} step={1} value={value} onChange={(e) => onChange(Number(e.target.value))} className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label={label} />
      <span className="w-9 shrink-0 text-right font-tabular text-sm font-semibold">{value}{suffix}</span>
    </div>
  )
}

export function RiskRewardDemo() {
  const [tp, setTp] = useState(60)
  const [sl, setSl] = useState(30)
  const [wr, setWr] = useState(50)
  const w = wr / 100
  const rr = riskRewardRatio(tp, sl)
  const ev = expectancy(w, rr)
  const be = breakEvenWinRate(rr)
  const tot = tp + sl

  return (
    <InteractiveCard
      title="盈亏比与期望"
      subtitle="拖止盈距离、止损距离、胜率,看盈亏比与期望联动。高盈亏比可容忍低胜率。"
    >
      <Slider label="止盈距离" value={tp} min={10} max={100} onChange={setTp} />
      <Slider label="止损距离" value={sl} min={10} max={100} onChange={setSl} />
      <Slider label="胜率" value={wr} min={5} max={95} onChange={setWr} suffix="%" />
      <div className="my-3 flex items-center gap-0.5">
        <div className="h-[26px] rounded-l bg-bear/20" style={{ width: Math.round((sl / tot) * 210) + 'px' }} />
        <div className="h-[34px] w-0.5 bg-foreground/40" />
        <div className="h-[26px] rounded-r bg-success/25" style={{ width: Math.round((tp / tot) * 210) + 'px' }} />
      </div>
      <div className="mb-2 grid grid-cols-3 gap-3">
        <div className="rounded-md bg-surface-subtle p-3.5">
          <div className="text-[13px] text-foreground/60">盈亏比</div>
          <div className="font-tabular text-2xl font-semibold">{rr.toFixed(2)}</div>
        </div>
        <div className="rounded-md bg-surface-subtle p-3.5">
          <div className="text-[13px] text-foreground/60">每笔期望(R)</div>
          <div className={'font-tabular text-2xl font-semibold ' + (ev >= 0 ? 'text-success' : 'text-midas-red')}>{ev >= 0 ? '+' : ''}{ev.toFixed(2)}</div>
        </div>
        <div className="rounded-md bg-surface-subtle p-3.5">
          <div className="text-[13px] text-foreground/60">保本胜率</div>
          <div className="font-tabular text-2xl font-semibold">{Math.round(be * 100)}%</div>
        </div>
      </div>
      <div className={'rounded px-3 py-2 text-sm ' + (ev >= 0 ? 'bg-success/10 text-success' : 'bg-midas-red/10 text-midas-red')}>
        {ev >= 0
          ? <>当前胜率 {Math.round(w * 100)}% ≥ 保本胜率 {Math.round(be * 100)}% → 长期<strong className="font-semibold">正期望</strong>(每笔约 +{ev.toFixed(2)}R)。高盈亏比把保本胜率压低了。</>
          : <>当前胜率 {Math.round(w * 100)}% ＜ 保本胜率 {Math.round(be * 100)}% → 长期<strong className="font-semibold">负期望</strong>(每笔约 {ev.toFixed(2)}R)。光有盈亏比、胜率不够也亏。</>}
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/50">
        配色:<span className="font-medium text-success">绿 = 正期望</span> · <span className="font-medium text-midas-red">红 = 负期望</span>(盈亏维度)。注:K线/指标篇用「涨红跌绿」表示价格方向,此处按盈亏好坏用绿/红,是两个维度。
      </p>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        <strong className="text-foreground/80">盈亏比 = 止盈距离 / 止损距离</strong>;期望(以止损=1R 计)= 胜率×盈亏比 − 败率。<strong className="text-foreground/80">保本胜率 = 1/(1+盈亏比)</strong>。盈亏比本身不保证盈利,要和胜率、执行一起看。
      </p>
    </InteractiveCard>
  )
}
