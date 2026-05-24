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
 * 占位(M2-B 数据缺口 · 上游未采集 · 绝不接真实数据 · 仅按目标样式画示意):
 *   ④ 多空人数比值(globalLongShortAccountRatio)→ 堆叠柱 + 比值线 示意
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

// 视觉 token(recharts 需 hex)
const C_LONG = '#1FA383' // 青绿 · 多 / 买
const C_SHORT = '#E8918C' // 浅红 · 空 / 卖
const C_RATIO = '#2A2A2A' // 深色 · 比值线
const C_GOLD = '#B8860B' // 帝王金
const C_RED = '#C8102E' // 中国红
const C_ORANGE = '#D97706' // 橙 · 基差率
const C_GRID = '#F0EEE8'
const C_AXIS = '#94949C'

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

const tooltipStyle = {
  fontSize: 11,
  borderRadius: 6,
  border: '1px solid #F0EEE8',
  padding: '4px 8px',
} as const
const legendStyle = { fontSize: 10 } as const

interface DimensionSectionProps {
  /** Binance Futures 风格 symbol · 'BTCUSDT' */
  futuresSymbol: string
}

export function DimensionSection({ futuresSymbol }: DimensionSectionProps) {
  // 288 点 = 24h @ 5min(任务4:数据点加密,曲线更细腻;采集 top100 扩容后历史变密)
  const oi = useOpenInterest(futuresSymbol, 288)
  const lsr = useLongShortRatio(futuresSymbol, 288)
  // ⑥ 基差(M2-C.2.4)· crypto_premium_index 每分钟一条 · 288 点 ≈ 近 5h
  const basis = useBasisSeries(futuresSymbol, 288)

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
  const accData = lsrItems.map((p) => toStack(p.top_account_long, p.top_account_short, p.top_account_ratio, p.ts))
  const posData = lsrItems.map((p) => toStack(p.top_position_long, p.top_position_short, p.top_position_ratio, p.ts))
  const takerData = lsrItems.map((p) => ({
    t: hhmm(p.ts), full: mmddhhmm(p.ts),
    buy: p.taker_buy_vol, sell: -p.taker_sell_vol, // sell 取负 · 对称展示
  }))

  const basisData = (basis.data?.items ?? []).map((p) => ({
    t: hhmm(p.ts), full: mmddhhmm(p.ts),
    mark: p.mark_price, index: p.index_price, basisPct: +p.basis_pct.toFixed(3),
  }))

  return (
    <div>
      <h3 className="mb-2 font-serif text-base font-bold">合约维度</h3>
      <div className="grid grid-cols-2 gap-4">
        {/* ① OI · 双指标双 Y 轴 */}
        <ChartCard title="① 合约持仓量(OI)" sub="持仓量(币)实线 / 持仓价值(USD)虚线 · 5min">
          <ChartState isLoading={oi.isPending} isError={oi.isError} isEmpty={oi.isSuccess && oiData.length === 0}>
            <OiChart data={oiData} />
          </ChartState>
        </ChartCard>

        {/* ② 大户多空比 · 账户数 */}
        <ChartCard title="② 大户多空比 · 账户数" sub="topLongShortAccountRatio · 多空占比 + 比值 · 5min">
          <ChartState isLoading={lsr.isPending} isError={lsr.isError} isEmpty={lsr.isSuccess && accData.length === 0}>
            <RatioStackChart data={accData} />
          </ChartState>
        </ChartCard>

        {/* ③ 大户多空比 · 持仓量 */}
        <ChartCard title="③ 大户多空比 · 持仓量" sub="topLongShortPositionRatio · 多空占比 + 比值 · 5min">
          <ChartState isLoading={lsr.isPending} isError={lsr.isError} isEmpty={lsr.isSuccess && posData.length === 0}>
            <RatioStackChart data={posData} />
          </ChartState>
        </ChartCard>

        {/* ④ 多空人数比值 · 占位(M2-B 待补)· 按目标样式画示意 */}
        <ChartCard title="④ 多空人数比值" sub="globalLongShortAccountRatio · 上游未采集" pending>
          <SchematicOverlay reason="数据源 M2-B 待补 · 仅示意样式 · 不接真实数据">
            <RatioStackChart data={SAMPLE_RATIO} />
          </SchematicOverlay>
        </ChartCard>

        {/* ⑤ 合约主动买卖量 · 对称双色柱 */}
        <ChartCard title="⑤ 合约主动买卖量" sub="taker 主买(青绿,上)/ 主卖(浅红,下)· 5min">
          <ChartState isLoading={lsr.isPending} isError={lsr.isError} isEmpty={lsr.isSuccess && takerData.length === 0}>
            <TakerChart data={takerData} />
          </ChartState>
        </ChartCard>

        {/* ⑥ 基差 · 真实(M2-C.2.4)· crypto_premium_index 每分钟 mark/index 时序 */}
        <ChartCard title="⑥ 基差(basis)" sub="合约价 / 指数价 / 基差率 · premiumIndex 每分钟">
          <ChartState isLoading={basis.isPending} isError={basis.isError} isEmpty={basis.isSuccess && basisData.length === 0}>
            <BasisChart data={basisData} />
          </ChartState>
        </ChartCard>
      </div>
    </div>
  )
}

// ── ① OI · 持仓量(币)实线 + 持仓价值(USD)虚线 · 双 Y 轴 ──────────────────
function OiChart({ data }: { data: { t: string; full: string; oi_coin: number; oi_usd: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={C_GRID} vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 9, fill: C_AXIS }} interval={xInterval(data.length)} minTickGap={36} tickLine={false} />
        <YAxis yAxisId="coin" width={42} tick={{ fontSize: 9, fill: C_AXIS }} tickFormatter={fmtCompact} domain={TIGHT_DOMAIN} />
        <YAxis yAxisId="usd" orientation="right" width={42} tick={{ fontSize: 9, fill: C_AXIS }} tickFormatter={fmtCompact} domain={TIGHT_DOMAIN} />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(_l, p) => (p?.[0]?.payload?.full ?? '')}
          formatter={(v, name) => [name === '持仓量(币)' ? fmtCompact(Number(v)) : `$${fmtCompact(Number(v))}`, name]}
        />
        <Legend wrapperStyle={legendStyle} iconSize={8} />
        <Line yAxisId="coin" type="monotone" dataKey="oi_coin" name="持仓量(币)" stroke={C_GOLD} strokeWidth={1.2} dot={false} />
        <Line yAxisId="usd" type="monotone" dataKey="oi_usd" name="持仓价值(USD)" stroke={C_RED} strokeWidth={1} strokeDasharray="4 3" dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── ②③④ · 多/空 堆叠柱(归一 100%)+ 比值线(右轴)──────────────────────────
function RatioStackChart({ data }: { data: { t: string; full: string; long: number; short: number; ratio: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={0}>
        <CartesianGrid stroke={C_GRID} vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 9, fill: C_AXIS }} interval={xInterval(data.length)} minTickGap={36} tickLine={false} />
        <YAxis yAxisId="pct" width={32} tick={{ fontSize: 9, fill: C_AXIS }} domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
        <YAxis yAxisId="ratio" orientation="right" width={34} tick={{ fontSize: 9, fill: C_AXIS }} domain={TIGHT_DOMAIN} tickFormatter={(v: number) => v.toFixed(2)} />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(_l, p) => (p?.[0]?.payload?.full ?? '')}
          formatter={(v, name) => [name === '比值' ? Number(v).toFixed(3) : `${Number(v).toFixed(1)}%`, name]}
        />
        <Legend wrapperStyle={legendStyle} iconSize={8} />
        <ReferenceLine yAxisId="ratio" y={1} stroke={C_AXIS} strokeDasharray="3 3" />
        <Bar yAxisId="pct" dataKey="long" name="多" stackId="ls" fill={C_LONG} />
        <Bar yAxisId="pct" dataKey="short" name="空" stackId="ls" fill={C_SHORT} />
        <Line yAxisId="ratio" type="monotone" dataKey="ratio" name="比值" stroke={C_RATIO} strokeWidth={1} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── ⑤ 主动买卖量 · 对称双色柱(buy 正 / sell 负)─────────────────────────────
function TakerChart({ data }: { data: { t: string; full: string; buy: number; sell: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={0} stackOffset="sign">
        <CartesianGrid stroke={C_GRID} vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 9, fill: C_AXIS }} interval={xInterval(data.length)} minTickGap={36} tickLine={false} />
        <YAxis width={42} tick={{ fontSize: 9, fill: C_AXIS }} tickFormatter={(v: number) => fmtCompact(Math.abs(v))} domain={TIGHT_DOMAIN} />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(_l, p) => (p?.[0]?.payload?.full ?? '')}
          formatter={(v, name) => [fmtCompact(Math.abs(Number(v))), name]}
        />
        <Legend wrapperStyle={legendStyle} iconSize={8} />
        <ReferenceLine y={0} stroke={C_AXIS} />
        <Bar dataKey="buy" name="主买" fill={C_LONG} stackId="taker" />
        <Bar dataKey="sell" name="主卖" fill={C_SHORT} stackId="taker" />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── ⑥ 基差 · 合约价 + 指数价 + 基差率(右轴橙线)· 占位示意 ────────────────────
function BasisChart({ data }: { data: { t: string; full: string; mark: number; index: number; basisPct: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={C_GRID} vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 9, fill: C_AXIS }} interval={xInterval(data.length)} minTickGap={36} tickLine={false} />
        <YAxis yAxisId="price" width={44} tick={{ fontSize: 9, fill: C_AXIS }} domain={TIGHT_DOMAIN} tickFormatter={fmtCompact} />
        <YAxis yAxisId="pct" orientation="right" width={36} tick={{ fontSize: 9, fill: C_AXIS }} domain={TIGHT_DOMAIN} tickFormatter={(v: number) => `${v.toFixed(2)}%`} />
        <Legend wrapperStyle={legendStyle} iconSize={8} />
        <Line yAxisId="price" type="monotone" dataKey="mark" name="合约价" stroke={C_GOLD} strokeWidth={1.2} dot={false} />
        <Line yAxisId="price" type="monotone" dataKey="index" name="指数价" stroke={C_RED} strokeWidth={1} strokeDasharray="4 3" dot={false} />
        <Line yAxisId="pct" type="monotone" dataKey="basisPct" name="基差率" stroke={C_ORANGE} strokeWidth={1} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── 占位示意外壳:渲染目标样式图(示意数据)· 压暗 + pointer 关 + 醒目标注 ──────
function SchematicOverlay({ reason, children }: { reason: string; children: React.ReactNode }) {
  return (
    <div className="relative h-full w-full">
      <div className="pointer-events-none h-full w-full opacity-40 grayscale">{children}</div>
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="rounded-md border border-dashed border-gold/60 bg-background/80 px-3 py-1.5 text-center">
          <div className="font-mono text-[11px] font-bold text-gold">数据 M2-B 待补</div>
          <div className="mt-0.5 text-[10px] text-muted-foreground/70">{reason}</div>
        </div>
      </div>
    </div>
  )
}

// ── 占位示意数据(确定性 · 仅用于画目标样式 · 已醒目标注「示意/待补」)──────────
const SAMPLE_RATIO = Array.from({ length: 24 }, (_, i) => {
  const long = 50 + 6 * Math.sin(i / 3) + 2
  const short = 100 - long
  return { t: '', full: '示意', long: +long.toFixed(1), short: +short.toFixed(1), ratio: +(long / short).toFixed(3) }
})

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
  isLoading, isError, isEmpty, children,
}: { isLoading: boolean; isError: boolean; isEmpty: boolean; children: React.ReactNode }) {
  if (isLoading) return <CenterNote>载入中…</CenterNote>
  if (isError) return <CenterNote>暂时无法读取(后端不可达)</CenterNote>
  if (isEmpty) return <CenterNote>暂无数据 · 预览环境未预热 / 待采集</CenterNote>
  return <>{children}</>
}

function CenterNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center rounded-md border border-dashed border-paper bg-background/60">
      <span className="text-[11px] text-muted-foreground/60">{children}</span>
    </div>
  )
}
