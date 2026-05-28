'use client'

/**
 * 设置页 · Bot 下单默认参数(后台预设)· 0026 G5 / 0027 MC-4(放开全仓选择)。
 *
 * bot 里「开多/开空」(永续)/「买入/卖出」(现货)用这套默认参数下单(全程 VIRTUAL·模拟)。
 * MC-4 起保证金模式 isolated / cross 可选 · 无预设行 = 默认逐仓(= G4/MC-3 行为)。
 */

import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import type { PerpMarginMode } from '@/lib/api/bot-preset'
import { useBotPreset, useSaveBotPreset } from '@/hooks/use-bot-preset'

export function BotOrderPresetSection() {
  const { data, isLoading } = useBotPreset()
  const save = useSaveBotPreset()

  const [leverage, setLeverage] = useState(3)
  const [perpNotional, setPerpNotional] = useState(100)
  const [marginMode, setMarginMode] = useState<PerpMarginMode>('isolated')
  const [cnyNotional, setCnyNotional] = useState(10000)
  const [usdNotional, setUsdNotional] = useState(1000)

  useEffect(() => {
    if (data) {
      setLeverage(data.perp_leverage)
      setPerpNotional(Number(data.perp_notional_usdt))
      setMarginMode(data.perp_margin_mode === 'cross' ? 'cross' : 'isolated')
      setCnyNotional(Number(data.spot_notional_cny))
      setUsdNotional(Number(data.spot_notional_usd))
    }
  }, [data])

  async function handleSave() {
    if (leverage < 1 || leverage > 20) {
      toast.error('杠杆需在 1–20x')
      return
    }
    if (perpNotional <= 0 || cnyNotional <= 0 || usdNotional <= 0) {
      toast.error('每单名义额需大于 0')
      return
    }
    try {
      await save.mutateAsync({
        perp_leverage: leverage,
        perp_notional_usdt: perpNotional,
        perp_margin_mode: marginMode,
        spot_notional_cny: cnyNotional,
        spot_notional_usd: usdNotional,
      })
      toast.success('Bot 下单默认参数已保存')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    }
  }

  if (isLoading) {
    return <p className="py-4 text-sm text-muted-foreground">载入中…</p>
  }

  return (
    <section className="mb-10">
      <h2 className="mb-2 font-serif text-xl font-bold text-foreground">
        Bot 下单默认参数
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">
        在 Telegram bot 里下单时套用这套默认参数(永续「开多/开空」· 现货「买入/卖出」)·
        全程 VIRTUAL · 模拟,仅供参考不构成投资建议
      </p>

      <div className="space-y-3 rounded-lg border border-paper bg-cream p-5 shadow-sm">
        <NumberField label="永续杠杆(1–20x)" value={leverage} onChange={setLeverage} min={1} max={20} step={1} />
        <NumberField label="永续每单名义额(USDT)" value={perpNotional} onChange={setPerpNotional} min={1} step={10} />
        <NumberField label="A股每单名义额(CNY)" value={cnyNotional} onChange={setCnyNotional} min={1} step={1000} />
        <NumberField label="美股每单名义额(USD)" value={usdNotional} onChange={setUsdNotional} min={1} step={100} />

        <div className="flex items-center gap-2 pt-1">
          <span className="text-sm text-muted-foreground">保证金模式</span>
          {(['isolated', 'cross'] as const).map((m) => {
            const active = marginMode === m
            const label = m === 'isolated' ? '逐仓' : '全仓'
            return (
              <button
                key={m}
                type="button"
                onClick={() => setMarginMode(m)}
                aria-pressed={active}
                className={
                  active
                    ? 'rounded border border-gold bg-gold/[0.08] px-2 py-0.5 font-mono text-[10px] text-gold'
                    : 'rounded border border-paper px-2 py-0.5 font-mono text-[10px] text-muted-foreground/70 hover:text-foreground hover:border-gold/40'
                }
              >
                {label}
              </button>
            )
          })}
          <span className="ml-1 text-[10px] text-muted-foreground/60">
            (同 symbol 不可混用 · 切模式前需先平掉该 symbol 活仓)
          </span>
        </div>

        <button
          type="button"
          onClick={handleSave}
          disabled={save.isPending}
          className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:cursor-not-allowed disabled:opacity-50"
        >
          {save.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          保存默认参数
        </button>
      </div>
    </section>
  )
}

interface NumberFieldProps {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
}

function NumberField({ label, value, onChange, min, max, step }: NumberFieldProps) {
  return (
    <label className="flex items-center justify-between gap-3">
      <span className="text-sm text-foreground">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-32 rounded-md border border-paper bg-background px-3 py-1.5 text-right font-mono text-sm text-foreground focus:border-midas-red focus:outline-none"
      />
    </label>
  )
}
