'use client'

/**
 * M2-D · 合约维度区 · 6 张图(专业样式版)。
 *
 * 接真实数据(M2-A 已验证表 · /api/v1/crypto/*):
 *   ① 合约持仓量(OI)     → crypto_open_interest      · 持仓量(币)实线 + 持仓价值(USD)虚线 · 双 Y 轴
 *   ② 大户多空比·账户数    → crypto_long_short_ratio   · 多/空 堆叠柱(归一 100%)+ 比值线
 *   ③ 大户多空比·持仓量    → crypto_long_short_ratio   · 同 ② 样式
 *   ⑤ 合约主动买卖量       → crypto_long_short_ratio   · 主买/主卖 对称双色柱(buy 正 / sell 负)
 *   ⑥ 基差(basis)        → crypto_premium_index      · 合约价 + 指数价 + 基差率 三线(M2-C.2.4 接真)
 *
 *   ④ 多空人数比值       → crypto_long_short_ratio   · 全市场账户多空占比 + 比值
 *
 * 配色:多/买 = 青绿 · 空/卖 = 浅红(跟点金涨跌语义区分:这是多空/买卖,不是涨跌)。
 *       #6482A0 缠论中枢专用色本模块禁用。
 * 状态契约:loading → 提示 · error / 空 → 「暂无数据」(不伪造)。
 */

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useBasisSeries, useLongShortRatio, useOpenInterest } from '@/hooks/use-crypto'
import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import type { Locale } from '@/i18n/routing'
import { type ChartColors, useChartColors } from '@/lib/chart-colors'

// 视觉 token(recharts 需 hex)· ★数据系列色固定(多空/OI/基差·中饱和·暗底也够清晰·不随主题)。
// ★暗黑 P1:容器色(网格/坐标轴/比值线/tooltip)改走 useChartColors 两套值(暗底不糊)。
const C_LONG = '#1FA383' // 青绿 · 多 / 买(多空≠涨跌 · 不随 color_pref 翻转)
const C_SHORT = '#E8918C' // 浅红 · 空 / 卖
const C_GOLD = '#B8860B' // 帝王金 · OI 量 / 合约价
const C_RED = '#C8102E' // 中国红 · OI 价值 / 指数价
const C_ORANGE = '#D97706' // 橙 · 基差率

const CHART_H = 'h-52'

// ── 时间格式 ────────────────────────────────────────────────────────────────
function hhmm(ts: string | number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
function mmddhhmm(ts: string | number): string {
  const d = new Date(ts)
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${hhmm(ts)}`
}
function fmtCompact(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return n.toFixed(2)
}
function sourceLabel(source: string | undefined, locale: Locale): string {
  const suffix = locale === 'en' ? 'Perpetuals' : '永续'
  if (!source) return locale === 'en' ? 'Perpetuals' : '永续合约'
  if (source.startsWith('Gate')) return `Gate ${suffix}`
  if (source.startsWith('Binance')) return `Binance ${suffix}`
  if (source.startsWith('OKX')) return `OKX ${suffix}`
  if (source.startsWith('Kraken')) return `Kraken ${suffix}`
  return locale === 'en' ? 'Perpetuals' : '永续合约'
}
// X 轴约 6 个刻度(数据点变密后仍保持清爽)· 配合 minTickGap 防重叠
function xInterval(len: number): number {
  return Math.max(0, Math.ceil(len / 6) - 1)
}

// 紧凑自适应 Y 量程(任务4):上下各留 ~0.3% 余量,让曲线占满图高、不被压成一条平线。
// 函数式 domain · recharts 对 min/max 两端分别回调。
const padMin = (m: number): number => (m >= 0 ? m * 0.997 : m * 1.003)
const padMax = (m: number): number => (m >= 0 ? m * 1.003 : m * 0.997)
// 给 recharts domain 用的函数对(成熟终端式紧凑量程)
const TIGHT_DOMAIN: [typeof padMin, typeof padMax] = [padMin, padMax]

// ★暗黑 P1:tooltip 背景/边框/文字随主题(暗底不再白底刺眼)
const TOOLTIP_BASE = { fontSize: 11, borderRadius: 6, padding: '4px 8px' } as const
function tipStyle(c: ChartColors) {
  return {
    ...TOOLTIP_BASE,
    backgroundColor: c.tooltipBg,
    border: `1px solid ${c.tooltipBorder}`,
    color: c.isDark ? '#E5E5E5' : '#1A1A1A',
  }
}
const legendStyle = { fontSize: 10 } as const

interface DimensionSectionProps {
  /** Binance Futures 风格 symbol · 'BTCUSDT' */
  futuresSymbol: string
}

export function DimensionSection({ futuresSymbol }: DimensionSectionProps) {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  // 288 点 = 24h @ 5min(任务4:数据点加密,曲线更细腻;采集 top100 扩容后历史变密)
  const oi = useOpenInterest(futuresSymbol, 288)
  const lsr = useLongShortRatio(futuresSymbol, 288)
  // ⑥ 基差(M2-C.2.4)· 标记价/指数价 5 分钟线 · 288 点 = 近 24h
  const basis = useBasisSeries(futuresSymbol, 288)
  const oiSource = sourceLabel(oi.data?.source, locale)
  const ratioSource = sourceLabel(lsr.data?.source, locale)
  const basisSource = sourceLabel(basis.data?.source, locale)

  const oiData = (oi.data?.items ?? []).map((p) => ({
    t: hhmm(p.ts), full: mmddhhmm(p.ts), oi_coin: p.oi_coin, oi_usd: p.oi_usd,
  }))

  const lsrItems = lsr.data?.items ?? []
  // 多/空归一到 100%(long+short 理论 ≈1,显式归一更稳)
  const toStack = (long: number, short: number, ratio: number, ts: string) => {
    const total = long + short || 1
    return {
      t: hhmm(ts), full: mmddhhmm(ts),
      long: +((long / total) * 100).toFixed(2),
      short: +((short / total) * 100).toFixed(2),
      ratio: +ratio.toFixed(3),
    }
  }
  const accData = lsrItems
    .filter((p) => p.top_account_ratio > 0)
    .map((p) => toStack(p.top_account_long, p.top_account_short, p.top_account_ratio, p.ts))
  const posData = lsrItems
    .filter((p) => p.top_position_ratio > 0)
    .map((p) => toStack(p.top_position_long, p.top_position_short, p.top_position_ratio, p.ts))
  // 刀C · ④ 全市场人数比:同一 lsr 响应映射(零新请求)· 过滤 global=0 老行(未采哨兵,真值恒 >0)
  const globalData = lsrItems
    .filter((p) => p.global_account_ratio > 0)
    .map((p) => toStack(p.global_account_long, p.global_account_short, p.global_account_ratio, p.ts))
  const takerData = lsrItems
    .filter((p) => p.taker_buy_vol > 0 || p.taker_sell_vol > 0)
    .map((p) => ({
      t: hhmm(p.ts), full: mmddhhmm(p.ts),
      buy: p.taker_buy_vol, sell: -p.taker_sell_vol, // sell 取负 · 对称展示
    }))

  const basisData = (basis.data?.items ?? []).map((p) => ({
    t: hhmm(p.ts), full: mmddhhmm(p.ts),
    mark: p.mark_price, index: p.index_price, basisPct: +p.basis_pct.toFixed(3),
  }))

  return (
    <div>
      <h3 className="mb-2 font-serif text-base font-bold">
        {en ? 'Perpetual metrics' : '合约维度'}
      </h3>
      {/* 移动刀C:窄屏单列(双列挤压 → X 轴时间标签重叠)· lg+ 恢复 2 列 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* ① OI · 双指标双 Y 轴 */}
        <ChartCard
          title={en ? '① Open interest (OI)' : '① 合约持仓量(OI)'}
          sub={en
            ? `${oiSource} · units (solid) / USD value (dashed) · 5 min`
            : `${oiSource} · 持仓量(币)实线 / 持仓价值(USD)虚线 · 5min`}
        >
          <ChartState locale={locale} isLoading={oi.isPending} isError={oi.isError} isEmpty={oi.isSuccess && oiData.length === 0}>
            <OiChart data={oiData} locale={locale} />
          </ChartState>
        </ChartCard>

        {/* ② 大户多空比 · 账户数 */}
        <ChartCard
          title={en ? '② Top traders · accounts' : '② 大户多空比 · 账户数'}
          sub={en
            ? `${ratioSource} · account long/short shares + ratio · 5 min`
            : `${ratioSource} · 大户账户多空占比 + 比值 · 5min`}
        >
          <ChartState locale={locale} isLoading={lsr.isPending} isError={lsr.isError} isEmpty={lsr.isSuccess && accData.length === 0}>
            <RatioStackChart data={accData} locale={locale} />
          </ChartState>
        </ChartCard>

        {/* ③ 大户多空比 · 持仓量 */}
        <ChartCard
          title={en ? '③ Top traders · positions' : '③ 大户多空比 · 持仓量'}
          sub={en
            ? `${ratioSource} · position long/short shares + ratio · 5 min`
            : `${ratioSource} · 大户持仓多空占比 + 比值 · 5min`}
        >
          <ChartState locale={locale} isLoading={lsr.isPending} isError={lsr.isError} isEmpty={lsr.isSuccess && posData.length === 0}>
            <RatioStackChart data={posData} locale={locale} />
          </ChartState>
        </ChartCard>

        {/* ④ 多空人数比值 · 真实数据(刀C · globalLongShortAccountRatio 全市场人数比) */}
        <ChartCard
          title={en ? '④ Global account ratio' : '④ 多空人数比值'}
          sub={en
            ? `${ratioSource} · market-wide long/short shares + ratio · 5 min`
            : `${ratioSource} · 全市场人数多空占比 + 比值 · 5min`}
        >
          <ChartState locale={locale} isLoading={lsr.isPending} isError={lsr.isError} isEmpty={lsr.isSuccess && globalData.length === 0}>
            <RatioStackChart data={globalData} locale={locale} />
          </ChartState>
        </ChartCard>

        {/* ⑤ 合约主动买卖量 · 对称双色柱 */}
        <ChartCard
          title={en ? '⑤ Taker buy / sell volume' : '⑤ 合约主动买卖量'}
          sub={en
            ? `${ratioSource} · taker buys (up) / sells (down) · 5 min`
            : `${ratioSource} · taker 主买(青绿,上)/ 主卖(浅红,下) · 5min`}
        >
          <ChartState locale={locale} isLoading={lsr.isPending} isError={lsr.isError} isEmpty={lsr.isSuccess && takerData.length === 0}>
            <TakerChart data={takerData} locale={locale} />
          </ChartState>
        </ChartCard>

        {/* ⑥ 基差 · 真实(M2-C.2.4)· 标记价/指数价 5 分钟时序 */}
        <ChartCard
          title={en ? '⑥ Basis' : '⑥ 基差(basis)'}
          sub={en
            ? `${basisSource} · mark / index / basis rate · 5 min`
            : `${basisSource} · 标记价 / 指数价 / 基差率 · 5min`}
        >
          <ChartState locale={locale} isLoading={basis.isPending} isError={basis.isError} isEmpty={basis.isSuccess && basisData.length === 0}>
            <BasisChart data={basisData} locale={locale} />
          </ChartState>
        </ChartCard>
      </div>
    </div>
  )
}

// ── ① OI · 持仓量(币)实线 + 持仓价值(USD)虚线 · 双 Y 轴 ──────────────────
function OiChart({ data, locale }: { data: { t: string; full: string; oi_coin: number; oi_usd: number }[]; locale: Locale }) {
  const c = useChartColors()
  const unitsLabel = locale === 'en' ? 'OI units' : '持仓量(币)'
  const valueLabel = locale === 'en' ? 'OI value (USD)' : '持仓价值(USD)'
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={c.grid} vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 9, fill: c.axisText }} interval={xInterval(data.length)} minTickGap={36} tickLine={false} />
        <YAxis yAxisId="coin" width={42} tick={{ fontSize: 9, fill: c.axisText }} tickFormatter={fmtCompact} domain={TIGHT_DOMAIN} />
        <YAxis yAxisId="usd" orientation="right" width={42} tick={{ fontSize: 9, fill: c.axisText }} tickFormatter={fmtCompact} domain={TIGHT_DOMAIN} />
        <Tooltip
          contentStyle={tipStyle(c)}
          labelFormatter={(_l, p) => (p?.[0]?.payload?.full ?? '')}
          formatter={(v, name) => [name === unitsLabel ? fmtCompact(Number(v)) : `$${fmtCompact(Number(v))}`, name]}
        />
        <Legend wrapperStyle={legendStyle} iconSize={8} />
        <Line yAxisId="coin" type="monotone" dataKey="oi_coin" name={unitsLabel} stroke={C_GOLD} strokeWidth={1.2} dot={false} />
        <Line yAxisId="usd" type="monotone" dataKey="oi_usd" name={valueLabel} stroke={C_RED} strokeWidth={1} strokeDasharray="4 3" dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── ②③④ · 多/空 堆叠柱(归一 100%)+ 比值线(右轴)──────────────────────────
function RatioStackChart({ data, locale }: { data: { t: string; full: string; long: number; short: number; ratio: number }[]; locale: Locale }) {
  const c = useChartColors()
  const longLabel = locale === 'en' ? 'Long' : '多'
  const shortLabel = locale === 'en' ? 'Short' : '空'
  const ratioLabel = locale === 'en' ? 'Ratio' : '比值'
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={0}>
        <CartesianGrid stroke={c.grid} vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 9, fill: c.axisText }} interval={xInterval(data.length)} minTickGap={36} tickLine={false} />
        <YAxis yAxisId="pct" width={32} tick={{ fontSize: 9, fill: c.axisText }} domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
        <YAxis yAxisId="ratio" orientation="right" width={34} tick={{ fontSize: 9, fill: c.axisText }} domain={TIGHT_DOMAIN} tickFormatter={(v: number) => v.toFixed(2)} />
        <Tooltip
          contentStyle={tipStyle(c)}
          labelFormatter={(_l, p) => (p?.[0]?.payload?.full ?? '')}
          formatter={(v, name) => [name === ratioLabel ? Number(v).toFixed(3) : `${Number(v).toFixed(1)}%`, name]}
        />
        <Legend wrapperStyle={legendStyle} iconSize={8} />
        <ReferenceLine yAxisId="ratio" y={1} stroke={c.axisText} strokeDasharray="3 3" />
        <Bar yAxisId="pct" dataKey="long" name={longLabel} stackId="ls" fill={C_LONG} />
        <Bar yAxisId="pct" dataKey="short" name={shortLabel} stackId="ls" fill={C_SHORT} />
        <Line yAxisId="ratio" type="monotone" dataKey="ratio" name={ratioLabel} stroke={c.neutral} strokeWidth={1} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── ⑤ 主动买卖量 · 对称双色柱(buy 正 / sell 负)─────────────────────────────
function TakerChart({ data, locale }: { data: { t: string; full: string; buy: number; sell: number }[]; locale: Locale }) {
  const c = useChartColors()
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={0} stackOffset="sign">
        <CartesianGrid stroke={c.grid} vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 9, fill: c.axisText }} interval={xInterval(data.length)} minTickGap={36} tickLine={false} />
        <YAxis width={42} tick={{ fontSize: 9, fill: c.axisText }} tickFormatter={(v: number) => fmtCompact(Math.abs(v))} domain={TIGHT_DOMAIN} />
        <Tooltip
          contentStyle={tipStyle(c)}
          labelFormatter={(_l, p) => (p?.[0]?.payload?.full ?? '')}
          formatter={(v, name) => [fmtCompact(Math.abs(Number(v))), name]}
        />
        <Legend wrapperStyle={legendStyle} iconSize={8} />
        <ReferenceLine y={0} stroke={c.axisText} />
        <Bar dataKey="buy" name={locale === 'en' ? 'Taker buy' : '主买'} fill={C_LONG} stackId="taker" />
        <Bar dataKey="sell" name={locale === 'en' ? 'Taker sell' : '主卖'} fill={C_SHORT} stackId="taker" />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── ⑥ 基差 · 合约价 + 指数价 + 基差率(右轴橙线)· 占位示意 ────────────────────
function BasisChart({ data, locale }: { data: { t: string; full: string; mark: number; index: number; basisPct: number }[]; locale: Locale }) {
  const c = useChartColors()
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={c.grid} vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 9, fill: c.axisText }} interval={xInterval(data.length)} minTickGap={36} tickLine={false} />
        <YAxis yAxisId="price" width={44} tick={{ fontSize: 9, fill: c.axisText }} domain={TIGHT_DOMAIN} tickFormatter={fmtCompact} />
        <YAxis yAxisId="pct" orientation="right" width={36} tick={{ fontSize: 9, fill: c.axisText }} domain={TIGHT_DOMAIN} tickFormatter={(v: number) => `${v.toFixed(2)}%`} />
        <Legend wrapperStyle={legendStyle} iconSize={8} />
        <Line yAxisId="price" type="monotone" dataKey="mark" name={locale === 'en' ? 'Mark price' : '合约价'} stroke={C_GOLD} strokeWidth={1.2} dot={false} />
        <Line yAxisId="price" type="monotone" dataKey="index" name={locale === 'en' ? 'Index price' : '指数价'} stroke={C_RED} strokeWidth={1} strokeDasharray="4 3" dot={false} />
        <Line yAxisId="pct" type="monotone" dataKey="basisPct" name={locale === 'en' ? 'Basis rate' : '基差率'} stroke={C_ORANGE} strokeWidth={1} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── 卡片外壳 ──────────────────────────────────────────────────────────────
function ChartCard({
  title, sub, pending = false, children,
}: { title: string; sub?: string; pending?: boolean; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-paper bg-surface-card p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-serif text-sm font-bold">{title}</span>
        {pending && (
          <span className="rounded bg-gold/15 px-1.5 py-0.5 text-[10px] text-gold">数据 M2-B 待补</span>
        )}
      </div>
      <div className={`${CHART_H} w-full`}>{children}</div>
      {sub && <div className="mt-1 text-[11px] text-muted-foreground/50">{sub}</div>}
    </div>
  )
}

// ── 状态包装 ──────────────────────────────────────────────────────────────
function ChartState({
  locale, isLoading, isError, isEmpty, children,
}: { locale: Locale; isLoading: boolean; isError: boolean; isEmpty: boolean; children: React.ReactNode }) {
  if (isLoading) return <CenterNote>{locale === 'en' ? 'Loading…' : '载入中…'}</CenterNote>
  if (isError) return <CenterNote>{locale === 'en' ? 'Data temporarily unavailable' : '暂时无法读取(后端不可达)'}</CenterNote>
  if (isEmpty) return <CenterNote>{locale === 'en' ? 'No data yet · warming up' : '暂无数据 · 预览环境未预热 / 待采集'}</CenterNote>
  return <>{children}</>
}

function CenterNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center rounded-md border border-dashed border-paper bg-background/60">
      <span className="text-[11px] text-muted-foreground/60">{children}</span>
    </div>
  )
}
