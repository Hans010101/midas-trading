'use client'

/**
 * M2-D · 合约维度区 · 6 张图。
 *
 * 接真实数据(M2-A 已验证有数据的表 · 经 /api/v1/crypto/* 读出):
 *   ① 合约持仓量(OI)         → crypto_open_interest        · oi_usd 面积图
 *   ② 大户多空比 · 账户数      → crypto_long_short_ratio     · top_account_ratio 线
 *   ③ 大户多空比 · 持仓量      → crypto_long_short_ratio     · top_position_ratio 线
 *   ⑤ 合约主动买卖量          → crypto_long_short_ratio     · taker_buy_vol / taker_sell_vol 双线
 *
 * 保持占位(M2-B 数据缺口 · 上游未采集 · 绝不硬接假数据):
 *   ④ 多空人数比值(globalLongShortAccountRatio)
 *   ⑥ 基差(basis · mark − index)
 *
 * 状态契约:loading → 骨架 · error / 空 → 「暂无数据」占位(不伪造)。
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useLongShortRatio, useOpenInterest } from '@/hooks/use-crypto'

// 视觉 token(recharts 需 hex)· #6482A0 是缠论中枢专用色,本模块禁用
const C_GOLD = '#B8860B' // 帝王金
const C_RED = '#C8102E' // 中国红
const C_BULL = '#DC143C' // 朱红(买/多)
const C_BEAR = '#0F6E5F' // 墨绿(卖/空)
const C_GRID = '#F0EEE8'
const C_AXIS = '#94949C'

const CHART_H = 'h-44'

function fmtTime(ts: string): string {
  const d = new Date(ts)
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function fmtCompact(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return n.toFixed(2)
}

interface DimensionSectionProps {
  /** Binance Futures 风格 symbol · 'BTCUSDT' */
  futuresSymbol: string
}

export function DimensionSection({ futuresSymbol }: DimensionSectionProps) {
  const oi = useOpenInterest(futuresSymbol, 96)
  const lsr = useLongShortRatio(futuresSymbol, 96)

  // OI 面积图数据
  const oiData =
    oi.data?.items.map((p) => ({ t: fmtTime(p.ts), oi_usd: p.oi_usd })) ?? []

  // 多空比 / taker 数据(同一份 long_short_ratio 拆三个图)
  const lsrItems = lsr.data?.items ?? []
  const accData = lsrItems.map((p) => ({ t: fmtTime(p.ts), ratio: p.top_account_ratio }))
  const posData = lsrItems.map((p) => ({ t: fmtTime(p.ts), ratio: p.top_position_ratio }))
  const takerData = lsrItems.map((p) => ({
    t: fmtTime(p.ts),
    buy: p.taker_buy_vol,
    sell: p.taker_sell_vol,
  }))

  return (
    <div>
      <h3 className="mb-2 font-serif text-base font-bold">合约维度</h3>
      <div className="grid grid-cols-2 gap-4">
        {/* ① OI */}
        <ChartCard title="① 合约持仓量(OI)" sub="oi_usd · 5min · 最近 8h">
          <ChartState
            isLoading={oi.isPending}
            isError={oi.isError}
            isEmpty={oi.isSuccess && oiData.length === 0}
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={oiData} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={C_GRID} vertical={false} />
                <XAxis dataKey="t" hide />
                <YAxis
                  width={48}
                  tick={{ fontSize: 10, fill: C_AXIS }}
                  tickFormatter={fmtCompact}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  formatter={(v) => [`$${fmtCompact(Number(v))}`, 'OI']}
                  contentStyle={tooltipStyle}
                />
                <Area
                  type="monotone"
                  dataKey="oi_usd"
                  stroke={C_GOLD}
                  fill={C_GOLD}
                  fillOpacity={0.15}
                  strokeWidth={1.5}
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </ChartState>
        </ChartCard>

        {/* ② 大户多空比 · 账户数 */}
        <ChartCard title="② 大户多空比 · 账户数" sub="topLongShortAccountRatio · 5min">
          <ChartState
            isLoading={lsr.isPending}
            isError={lsr.isError}
            isEmpty={lsr.isSuccess && accData.length === 0}
          >
            <RatioChart data={accData} color={C_RED} />
          </ChartState>
        </ChartCard>

        {/* ③ 大户多空比 · 持仓量 */}
        <ChartCard title="③ 大户多空比 · 持仓量" sub="topLongShortPositionRatio · 5min">
          <ChartState
            isLoading={lsr.isPending}
            isError={lsr.isError}
            isEmpty={lsr.isSuccess && posData.length === 0}
          >
            <RatioChart data={posData} color={C_GOLD} />
          </ChartState>
        </ChartCard>

        {/* ④ 多空人数比值 · 占位(M2-B 待补)*/}
        <ChartCard title="④ 多空人数比值" sub="globalLongShortAccountRatio · 上游未采集" pending>
          <PendingPlaceholder reason="数据源 M2-B 待补 · 不接假数据" />
        </ChartCard>

        {/* ⑤ 合约主动买卖量 */}
        <ChartCard title="⑤ 合约主动买卖量" sub="taker buy(朱红)/ sell(墨绿)· 5min">
          <ChartState
            isLoading={lsr.isPending}
            isError={lsr.isError}
            isEmpty={lsr.isSuccess && takerData.length === 0}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={takerData} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={C_GRID} vertical={false} />
                <XAxis dataKey="t" hide />
                <YAxis
                  width={48}
                  tick={{ fontSize: 10, fill: C_AXIS }}
                  tickFormatter={fmtCompact}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  formatter={(v, name) => [fmtCompact(Number(v)), name === 'buy' ? '主买' : '主卖']}
                  contentStyle={tooltipStyle}
                />
                <Line type="monotone" dataKey="buy" stroke={C_BULL} strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="sell" stroke={C_BEAR} strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartState>
        </ChartCard>

        {/* ⑥ 基差 · 占位(M2-B 待补)*/}
        <ChartCard title="⑥ 基差(basis)" sub="mark − index · 上游未采集" pending>
          <PendingPlaceholder reason="数据源 M2-B 待补 · 不接假数据" />
        </ChartCard>
      </div>
    </div>
  )
}

// ── 比值折线图(账户/持仓多空比共用 · 含 1.0 平衡参考线)──────────────────
function RatioChart({ data, color }: { data: { t: string; ratio: number }[]; color: string }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={C_GRID} vertical={false} />
        <XAxis dataKey="t" hide />
        <YAxis
          width={36}
          tick={{ fontSize: 10, fill: C_AXIS }}
          tickFormatter={(v: number) => v.toFixed(2)}
          domain={['auto', 'auto']}
        />
        <Tooltip
          formatter={(v) => [Number(v).toFixed(3), '多空比']}
          contentStyle={tooltipStyle}
        />
        <ReferenceLine y={1} stroke={C_AXIS} strokeDasharray="3 3" />
        <Line type="monotone" dataKey="ratio" stroke={color} strokeWidth={1.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

const tooltipStyle = {
  fontSize: 11,
  borderRadius: 6,
  border: '1px solid #F0EEE8',
  padding: '4px 8px',
} as const

// ── 卡片外壳 ──────────────────────────────────────────────────────────────
function ChartCard({
  title,
  sub,
  pending = false,
  children,
}: {
  title: string
  sub?: string
  pending?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-paper bg-cream/30 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-serif text-sm font-bold">{title}</span>
        {pending && (
          <span className="rounded bg-gold/15 px-1.5 py-0.5 text-[10px] text-gold">
            数据 M2-B 待补
          </span>
        )}
      </div>
      <div className={`${CHART_H} w-full`}>{children}</div>
      {sub && <div className="mt-1 text-[11px] text-muted-foreground/50">{sub}</div>}
    </div>
  )
}

// ── 状态包装:loading / error / empty / 正常 ──────────────────────────────
function ChartState({
  isLoading,
  isError,
  isEmpty,
  children,
}: {
  isLoading: boolean
  isError: boolean
  isEmpty: boolean
  children: React.ReactNode
}) {
  if (isLoading) {
    return <CenterNote>加载中…</CenterNote>
  }
  if (isError) {
    return <CenterNote>暂时无法读取(后端不可达)</CenterNote>
  }
  if (isEmpty) {
    return <CenterNote>暂无数据 · 预览环境未预热 / 待采集</CenterNote>
  }
  return <>{children}</>
}

function PendingPlaceholder({ reason }: { reason: string }) {
  return (
    <div className="flex h-full items-center justify-center rounded-md border border-dashed border-paper bg-background/60">
      <div className="text-center">
        <div className="font-mono text-xs text-muted-foreground/60">[ 待 M2-B 接入 ]</div>
        <div className="mt-1 text-[11px] text-gold/80">{reason}</div>
      </div>
    </div>
  )
}

function CenterNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center rounded-md border border-dashed border-paper bg-background/60">
      <span className="text-[11px] text-muted-foreground/60">{children}</span>
    </div>
  )
}
