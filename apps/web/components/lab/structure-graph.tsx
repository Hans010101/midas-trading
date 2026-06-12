'use client'

/**
 * 因子关联图谱(沙盘助手二期刀1 · 结构沙盘视觉主体)。
 *
 * 纯 SVG + 预设圆形布局(节点 ≤10 · 零新依赖 · 渲染确定):
 *   节点 = 因子(状态色:偏多朱红 / 偏空墨绿 / 中性灰;LLM 点名背离/极端 → 金环);
 *   边 = 规则推导(lib/structure-graph)· 背离 = 帝王金虚线脉冲 · 共振 = 朱红/墨绿实线;
 *   tooltip = SVG 原生 <title>(边带「规则推导」署名 · 节点带「LLM 判定」署名 · 分层语义)。
 * 节点数按 snapshot 非空因子自适应角度(三期扩到 10 因子无需改布局)。
 * 🔴 红线:纯展示 · 输入 = diag.snapshot + factor_findings 已有数据 · services/structure 零碰。
 */

import type { FactorFinding, StructureSnapshot } from '@/lib/api/structure'
import { FACTOR_LABEL, FACTOR_ORDER, deriveGraphEdges } from '@/lib/structure-graph'
import { TONE_HEX, factorHeadline, isDivergentFinding } from '@/lib/structure-viz'

// 设计 token(SVG 内用 hex):朱红/墨绿=全站涨跌 · 帝王金=警示 · ⛔ 缠论淡灰蓝不可挪用
const C_BULL = '#DC143C'
const C_BEAR = '#0F6E5F'
const C_GOLD = '#B8860B'
const C_NEUTRAL = '#9A938A'

const W = 360
const H = 300
const CX = W / 2
const CY = H / 2
const R = 100 // 节点圆周半径(刀2:节点加大 + 标签两行,半径略收防溢出)

interface NodeSpec {
  key: string
  label: string
  x: number
  y: number
  color: string
  divergent: boolean
  stateText: string | null
  /** 刀2:节点第二行数值(snapshot 结构化字段 · 灰中性节点也有信息量) */
  valueText: string | null
  valueHex: string
}

function stanceColor(state: string | undefined): string {
  if (!state) return C_NEUTRAL
  if (/多/.test(state)) return C_BULL
  if (/空/.test(state)) return C_BEAR
  return C_NEUTRAL
}

interface StructureGraphProps {
  snapshot: StructureSnapshot
  findings: FactorFinding[]
}

export function StructureGraph({ snapshot, findings }: StructureGraphProps) {
  const present = FACTOR_ORDER.filter(
    (k) => (snapshot as unknown as Record<string, unknown>)[k] != null,
  )
  if (present.length === 0) return null

  const byFactor = new Map(findings.map((f) => [f.factor, f]))
  const nodes: NodeSpec[] = present.map((key, i) => {
    // 从正上方起顺时针均布(-90° 起)· 角度随节点数自适应
    const angle = (-90 + (360 / present.length) * i) * (Math.PI / 180)
    const f = byFactor.get(key)
    const head = factorHeadline(key, snapshot)
    return {
      key,
      label: FACTOR_LABEL[key] ?? key,
      x: CX + R * Math.cos(angle),
      y: CY + R * Math.sin(angle),
      color: stanceColor(f?.state),
      divergent: f != null && isDivergentFinding(f),
      stateText: f?.state ?? null,
      valueText: head?.text ?? null,
      valueHex: head ? TONE_HEX[head.tone] : C_NEUTRAL,
    }
  })
  const pos = new Map(nodes.map((n) => [n.key, n]))

  // 边:两端节点都在场才画(缺因子的边由规则层已跳过 · 双保险)
  const edges = deriveGraphEdges(snapshot).filter((e) => pos.has(e.from) && pos.has(e.to))
  const nDiv = edges.filter((e) => e.type === 'divergence').length
  const nRes = edges.length - nDiv

  return (
    <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <svg viewBox={`0 0 ${W} ${H}`} className="mx-auto block w-full max-w-md" role="img">
        {/* ── 边(先画 · 压在节点下)────────────────────────────── */}
        {edges.map((e, i) => {
          const a = pos.get(e.from)!
          const b = pos.get(e.to)!
          const stroke =
            e.type === 'divergence' ? C_GOLD : e.direction === 'bear' ? C_BEAR : C_BULL
          return (
            <line
              key={`${e.from}-${e.to}-${i}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={stroke}
              strokeWidth={e.type === 'divergence' ? 2 : 1.6}
              strokeDasharray={e.type === 'divergence' ? '6 4' : undefined}
              opacity={0.85}
            >
              {/* 背离边:dashoffset 循环 = 金色脉冲流动(SVG 原生动画 · 零 CSS 依赖) */}
              {e.type === 'divergence' && (
                <animate attributeName="stroke-dashoffset" from="20" to="0" dur="1.2s" repeatCount="indefinite" />
              )}
              <title>{`${e.reason}(规则推导)`}</title>
            </line>
          )
        })}

        {/* ── 节点(刀2:加大 + 第二行数值 · 灰中性节点也有信息量)──────── */}
        {nodes.map((n) => {
          const labelAbove = n.y <= CY
          const labelY = labelAbove ? n.y - 24 : n.y + 32
          const valueY = labelAbove ? n.y - 35 : n.y + 44
          return (
            <g key={n.key}>
              {/* LLM 点名背离/极端 → 金环 */}
              {n.divergent && (
                <circle cx={n.x} cy={n.y} r={16} fill="none" stroke={C_GOLD} strokeWidth={2} />
              )}
              <circle cx={n.x} cy={n.y} r={12} fill={n.color} opacity={0.92}>
                <title>
                  {n.stateText ? `${n.label}:${n.stateText}(LLM 判定)` : `${n.label}:未点名`}
                </title>
              </circle>
              <text
                x={n.x}
                y={labelY}
                textAnchor="middle"
                fontSize={10}
                fill="currentColor"
                className="text-muted-foreground"
              >
                {n.label}
              </text>
              {n.valueText && (
                <text
                  x={n.x}
                  y={valueY}
                  textAnchor="middle"
                  fontSize={9}
                  fontFamily="var(--font-mono, monospace)"
                  fontWeight={700}
                  fill={n.valueHex}
                >
                  {n.valueText}
                </text>
              )}
            </g>
          )
        })}

        {/* ── 中心:symbol + 边统计 ───────────────────────────── */}
        <text x={CX} y={CY - 4} textAnchor="middle" fontSize={15} fontWeight={700} fill="currentColor">
          {snapshot.symbol}
        </text>
        <text x={CX} y={CY + 14} textAnchor="middle" fontSize={10} fill={edges.length > 0 ? C_GOLD : C_NEUTRAL}>
          {edges.length > 0 ? `${nDiv} 背离 · ${nRes} 共振` : '无显著背离/共振'}
        </text>
      </svg>

      {/* 图例 + 署名(边=规则 · 节点=LLM 两层语义,明示来源) */}
      <div className="mt-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[10px] text-muted-foreground/70">
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-4" style={{ background: C_GOLD }} />
          背离(规则推导)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-4" style={{ background: C_BULL }} />
          偏多共振
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-4" style={{ background: C_BEAR }} />
          偏空共振
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block size-2 rounded-full border-2" style={{ borderColor: C_GOLD }} />
          LLM 点名背离/极端
        </span>
      </div>
    </div>
  )
}
