'use client'

/**
 * 迷你时序图(沙盘助手第一期)· Recharts 裸轴 · 7 因子卡共用。
 *
 * 数据旁路取自 crypto 现有端点(不进诊断链)· 数据未到/不足 2 点 → 返回 null
 * (卡片仍显示文字 · 优雅降级不破版式)。
 */

import { Line, LineChart, ResponsiveContainer, YAxis } from 'recharts'

export interface SparkPoint {
  t: string
  v: number
}

interface SparklineProps {
  data: SparkPoint[]
  /** 线色 · 默认帝王金(结构数据中性强调色 · ⛔ 缠论淡灰蓝专用不可挪用) */
  stroke?: string
}

export function Sparkline({ data, stroke = '#B8860B' }: SparklineProps) {
  if (data.length < 2) return null
  return (
    <div className="h-10 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
          {/* 裸轴:domain 贴数据 · 不渲染坐标轴/网格/tooltip(迷你图只看形状) */}
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Line type="monotone" dataKey="v" stroke={stroke} strokeWidth={1.2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
