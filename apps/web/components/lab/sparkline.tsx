'use client'

/**
 * 迷你时序图(沙盘助手第一期)· Recharts 裸轴 · 7 因子卡共用。
 *
 * 数据旁路取自 crypto 现有端点(不进诊断链)· 数据未到/不足 2 点 → 返回 null
 * (卡片仍显示文字 · 优雅降级不破版式)。
 */

import { Line, LineChart, ReferenceLine, ResponsiveContainer, YAxis } from 'recharts'

export interface SparkPoint {
  t: string
  v: number
}

interface SparklineProps {
  data: SparkPoint[]
  /** 线色 · 默认帝王金;二期刀2 起由 sparklineSpec 按因子语义传(朱红/墨绿/灰) */
  stroke?: string
  /** 语义基准线(费率/基差 0 轴 · 多空比 1.0 轴)· 淡灰细虚线 · 省略不画 */
  baseline?: number
}

export function Sparkline({ data, stroke = '#B8860B', baseline }: SparklineProps) {
  if (data.length < 2) return null
  return (
    <div className="h-10 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
          {/* 裸轴:domain 贴数据(含 baseline,保证基准线可见)· 无网格/tooltip */}
          <YAxis
            hide
            domain={
              baseline != null
                ? [(min: number) => Math.min(min, baseline), (max: number) => Math.max(max, baseline)]
                : ['dataMin', 'dataMax']
            }
          />
          {baseline != null && (
            <ReferenceLine y={baseline} stroke="#C9C2B8" strokeWidth={0.8} strokeDasharray="3 3" />
          )}
          <Line type="monotone" dataKey="v" stroke={stroke} strokeWidth={1.2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
