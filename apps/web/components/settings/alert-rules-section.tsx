'use client'

/**
 * 设置页 · 告警规则配置 · 0026 G5 · DP-G5-2/3。
 *
 * 复用 G2b CRUD + G5 一键应用推荐。指标按 /indicators 目录动态渲染(当前 20 个)。
 * 全程仅作提示。
 */

import { Loader2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import {
  useAlertRules,
  useApplyRecommended,
  useCreateAlertRule,
  useDeleteAlertRule,
  useIndicators,
  useSetAlertRuleEnabled,
} from '@/hooks/use-alert-rules'
import type { IndicatorMeta, Operator } from '@/lib/api/alert-rules'

const MARKET_LABEL: Record<string, { en: string; zh: string }> = {
  cn: { en: 'A-shares', zh: 'A股' },
  us: { en: 'U.S. stocks', zh: '美股' },
  crypto: { en: 'Crypto', zh: '加密' },
  hk: { en: 'Hong Kong stocks', zh: '港股' },
}
const INDICATOR_LABEL_EN: Record<string, string> = {
  price: 'Latest price',
  price_change_pct: 'Change %',
  volume: 'Volume',
  ma_5: 'MA5',
  ma_20: 'MA20',
  ma_60: 'MA60',
  macd_hist: 'MACD histogram',
  rsi_14: 'RSI(14)',
  boll_pctb: 'Bollinger %B',
  chan_buy: 'Chan Theory buy point',
  chan_sell: 'Chan Theory sell point',
  funding_rate: 'Funding rate',
  open_interest_usd: 'Open interest (USD)',
  long_short_ratio: 'Long/short ratio (top accounts)',
  basis_pct: 'Basis %',
  fear_greed: 'Fear & Greed index',
  btc_dominance: 'BTC dominance %',
  cn_breadth_up_ratio: 'A-share advancers ratio %',
  hk_breadth_up_ratio: 'Hong Kong advancers ratio %',
  sector_change_pct: 'Sector change %',
  index_change_pct: 'Index change %',
}
const OP_LABEL: Record<Operator, string> = { gt: '>', gte: '≥', lt: '<', lte: '≤' }
const MAX_RULES = 20

export function AlertRulesSection() {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const { data: indicators } = useIndicators()
  const { data: rules, isLoading } = useAlertRules()
  const apply = useApplyRecommended()
  const remove = useDeleteAlertRule()
  const toggle = useSetAlertRuleEnabled()

  const indMap = useMemo(
    () => new Map((indicators ?? []).map((i) => [i.key, i])),
    [indicators],
  )

  async function handleApply() {
    try {
      const r = await apply.mutateAsync()
      toast.success(
        en
          ? `Recommended rules applied: ${r.created} added · ${r.skipped} skipped`
          : `已应用推荐规则:新增 ${r.created} 条 · 跳过 ${r.skipped} 条`,
      )
    } catch (e) {
      toast.error(e instanceof Error ? e.message : en ? 'Unable to apply rules' : '应用失败')
    }
  }

  return (
    <section className="mb-10">
      <h2 className="mb-2 font-serif text-xl font-bold text-foreground">
        {en ? 'Alert rules' : '告警规则'}
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">
        {en
          ? `Matched rules are sent through Telegram after binding · Up to ${MAX_RULES} rules`
          : `命中规则会经 Telegram 推送(需先绑定)· 上限 ${MAX_RULES} 条`}
      </p>

      <div className="mb-4 rounded-lg border border-gold/40 bg-gold/[0.06] p-4">
        <p className="mb-2 text-sm text-foreground">
          {en
            ? 'Start with a curated rule set covering Fear & Greed extremes, broad A-share declines and leader RSI thresholds.'
            : '新手不知从何下手?一键应用一套推荐规则(恐贪极值 / A股普跌 / 龙头 RSI 超买超卖)。'}
        </p>
        <button
          type="button"
          onClick={handleApply}
          disabled={apply.isPending}
          className="inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:opacity-50"
        >
          {apply.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {en ? '✨ Apply recommended rules' : '✨ 一键应用推荐规则'}
        </button>
      </div>

      {/* 现有规则 */}
      <div className="mb-4 space-y-2">
        {isLoading && (
          <p className="text-sm text-muted-foreground">{en ? 'Loading…' : '载入中…'}</p>
        )}
        {!isLoading && (rules?.length ?? 0) === 0 && (
          <p className="text-sm text-muted-foreground/70">
            {en
              ? 'No rules yet. Apply the recommended set or create one below.'
              : '还没有规则。用上方一键应用,或在下方添加。'}
          </p>
        )}
        {rules?.map((rule) => {
          const meta = indMap.get(rule.indicator)
          const marketLabel = MARKET_LABEL[rule.market]
          const target = rule.symbol ?? (marketLabel ? marketLabel[en ? 'en' : 'zh'] : rule.market)
          const unit = meta?.unit ?? ''
          const label = en
            ? INDICATOR_LABEL_EN[rule.indicator] ?? rule.indicator.replaceAll('_', ' ')
            : meta?.label ?? rule.indicator
          return (
            <div
              key={rule.id}
              className="flex items-center justify-between gap-2 rounded-md border border-paper bg-cream px-3 py-2"
            >
              <span className="text-sm text-foreground">
                {label} {OP_LABEL[rule.operator]} {rule.threshold}
                {unit} · {target}
              </span>
              <div className="flex items-center gap-2">
                <label className="flex cursor-pointer items-center gap-1 font-mono text-[10px]">
                  <input
                    type="checkbox"
                    checked={rule.enabled}
                    onChange={(e) =>
                      toggle.mutate({ id: rule.id, enabled: e.target.checked })
                    }
                    className="h-3.5 w-3.5 accent-midas-red"
                  />
                  <span className={rule.enabled ? 'text-midas-red' : 'text-muted-foreground/50'}>
                    {rule.enabled ? (en ? 'Enabled' : '启用') : en ? 'Disabled' : '停用'}
                  </span>
                </label>
                <button
                  type="button"
                  onClick={() => remove.mutate(rule.id)}
                  className="text-muted-foreground/60 transition-colors hover:text-midas-red"
                  aria-label={en ? 'Delete rule' : '删除规则'}
                >
                  ✕
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* 添加规则 */}
      <AddRuleForm
        indicators={indicators ?? []}
        disabled={(rules?.length ?? 0) >= MAX_RULES}
        en={en}
      />
    </section>
  )
}

function AddRuleForm({
  indicators,
  disabled,
  en,
}: {
  indicators: IndicatorMeta[]
  disabled: boolean
  en: boolean
}) {
  const create = useCreateAlertRule()
  const [indicatorKey, setIndicatorKey] = useState('')
  const [market, setMarket] = useState('')
  const [symbol, setSymbol] = useState('')
  const [operator, setOperator] = useState<Operator>('gt')
  const [threshold, setThreshold] = useState('')

  const meta = indicators.find((i) => i.key === indicatorKey)

  function onIndicatorChange(key: string) {
    setIndicatorKey(key)
    const m = indicators.find((i) => i.key === key)
    setMarket(m?.markets[0] ?? '')
    setSymbol('')
  }

  async function onAdd() {
    if (!meta || !market) {
      toast.error(en ? 'Select an indicator and market' : '请选择指标和市场')
      return
    }
    if (meta.requires_symbol && !symbol.trim()) {
      toast.error(en ? 'This indicator requires a symbol' : '该指标需要标的代码')
      return
    }
    const th = Number(threshold)
    if (Number.isNaN(th) || threshold.trim() === '') {
      toast.error(en ? 'Enter a threshold' : '请输入阈值')
      return
    }
    try {
      await create.mutateAsync({
        market,
        symbol: meta.requires_symbol ? symbol.trim() : null,
        indicator: indicatorKey,
        operator,
        threshold: th,
        timeframe: meta.needs_timeframe ? '1d' : null,
      })
      toast.success(en ? 'Rule added' : '规则已添加')
      setIndicatorKey('')
      setMarket('')
      setSymbol('')
      setThreshold('')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : en ? 'Unable to add rule' : '添加失败')
    }
  }

  if (disabled) {
    return (
      <p className="rounded-md border border-paper bg-cream px-3 py-2 text-xs text-muted-foreground">
        {en
          ? `You have reached the ${MAX_RULES}-rule limit · Delete a rule to add another.`
          : `已达 ${MAX_RULES} 条上限 · 删除部分规则后可继续添加。`}
      </p>
    )
  }

  return (
    <div className="space-y-2 rounded-lg border border-paper bg-cream p-4">
      <h3 className="text-sm font-medium text-foreground">
        {en ? 'Add rule' : '添加规则'}
      </h3>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={indicatorKey}
          onChange={(e) => onIndicatorChange(e.target.value)}
          className="rounded-md border border-paper bg-background px-2 py-1.5 text-sm"
        >
          <option value="">{en ? 'Select indicator…' : '选指标…'}</option>
          {indicators.map((i) => (
            <option key={i.key} value={i.key}>
              {en ? INDICATOR_LABEL_EN[i.key] ?? i.key.replaceAll('_', ' ') : i.label}
            </option>
          ))}
        </select>

        {meta && (
          <select
            value={market}
            onChange={(e) => setMarket(e.target.value)}
            className="rounded-md border border-paper bg-background px-2 py-1.5 text-sm"
          >
            {meta.markets.map((m) => (
              <option key={m} value={m}>
                {MARKET_LABEL[m]?.[en ? 'en' : 'zh'] ?? m}
              </option>
            ))}
          </select>
        )}

        {meta?.requires_symbol && (
          <input
            type="text"
            value={symbol}
            placeholder={en ? 'Symbol, e.g. NVDA' : '代码 如 NVDA'}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-28 rounded-md border border-paper bg-background px-2 py-1.5 text-sm"
          />
        )}

        <select
          value={operator}
          onChange={(e) => setOperator(e.target.value as Operator)}
          className="rounded-md border border-paper bg-background px-2 py-1.5 text-sm"
        >
          {(['gt', 'gte', 'lt', 'lte'] as Operator[]).map((op) => (
            <option key={op} value={op}>
              {OP_LABEL[op]}
            </option>
          ))}
        </select>

        <input
          type="number"
          value={threshold}
          placeholder={en ? 'Threshold' : '阈值'}
          onChange={(e) => setThreshold(e.target.value)}
          className="w-24 rounded-md border border-paper bg-background px-2 py-1.5 text-right font-mono text-sm"
        />

        <button
          type="button"
          onClick={onAdd}
          disabled={create.isPending}
          className="inline-flex items-center gap-1.5 rounded-md border border-midas-red/40 bg-background px-3 py-1.5 text-sm text-midas-red transition-colors hover:bg-midas-red/[0.06] disabled:opacity-50"
        >
          {create.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {en ? 'Add' : '添加'}
        </button>
      </div>
      {meta?.needs_timeframe && (
        <p className="text-[11px] text-muted-foreground/70">
          {en ? 'Calculated on the daily (1d) timeframe' : '该指标按日线(1d)计算'}
        </p>
      )}
    </div>
  )
}
