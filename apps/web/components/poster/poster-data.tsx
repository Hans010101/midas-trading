'use client'

/** 版二「数据美学」· product-forward,factor-graph hero(Design poster-data.jsx 移植)。1080×1920。 */

import { BRAND, Seal } from '@/components/poster/brand'
import { PosterQR } from '@/components/poster/poster-qr'
import type { PosterProps } from '@/components/poster/types'

// 风格化因子关联图谱(艺术再现 · 非截图)
function FactorGraph({ size = 700 }: { size?: number }) {
  const B = BRAND
  const C = size / 2
  const R = size * 0.355
  const factors = [
    { t: '多空比', k: 'r' }, { t: '资金费率', k: 'g' }, { t: '持仓量', k: 'r' },
    { t: '基差', k: 'g' }, { t: '情绪', k: 'r' }, { t: '波动率', k: 'g' },
    { t: '主力净流', k: 'r' }, { t: '成交量', k: 'g' }, { t: '趋势', k: 'r' },
  ]
  const n = factors.length
  const pts = factors.map((f, i) => {
    const a = -Math.PI / 2 + (i / n) * Math.PI * 2
    return { ...f, x: C + R * Math.cos(a), y: C + R * Math.sin(a), a }
  })
  // 共振 = solid (red/green),背离 = gold dashed
  const edges = [
    { a: 0, b: 2, type: 's', c: B.red },
    { a: 4, b: 8, type: 's', c: B.red },
    { a: 1, b: 7, type: 's', c: B.inkGreen },
    { a: 3, b: 5, type: 's', c: B.inkGreen },
    { a: 0, b: 4, type: 'd' },
    { a: 2, b: 6, type: 'd' },
    { a: 1, b: 3, type: 'd' },
    { a: 5, b: 8, type: 'd' },
    { a: 6, b: 8, type: 's', c: B.red },
  ]
  const dotR = size * 0.052
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <radialGradient id="fg-core" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={B.red} stopOpacity="0.16" />
          <stop offset="70%" stopColor={B.red} stopOpacity="0.03" />
          <stop offset="100%" stopColor={B.red} stopOpacity="0" />
        </radialGradient>
        <radialGradient id="fg-red" cx="38%" cy="34%" r="72%">
          <stop offset="0%" stopColor="#E33A52" />
          <stop offset="100%" stopColor={B.red} />
        </radialGradient>
        <radialGradient id="fg-grn" cx="38%" cy="34%" r="72%">
          <stop offset="0%" stopColor="#1B8C78" />
          <stop offset="100%" stopColor={B.inkGreen} />
        </radialGradient>
      </defs>

      {/* radar rings + core */}
      <circle cx={C} cy={C} r={R * 1.18} fill="url(#fg-core)" />
      {[R * 0.46, R * 0.82, R].map((r, i) => (
        <circle key={i} cx={C} cy={C} r={r} fill="none" stroke="rgba(28,24,21,.10)" strokeWidth="1" />
      ))}
      {pts.map((p, i) => (
        <line key={`spoke-${i}`} x1={C} y1={C} x2={p.x} y2={p.y} stroke="rgba(28,24,21,.06)" strokeWidth="1" />
      ))}

      {/* edges */}
      {edges.map((e, i) => {
        const p = pts[e.a]
        const q = pts[e.b]
        if (e.type === 'd')
          return (
            <line
              key={`e-${i}`}
              x1={p.x} y1={p.y} x2={q.x} y2={q.y}
              stroke={B.gold} strokeWidth="2.2" strokeDasharray="3 7" strokeLinecap="round"
              style={{ animation: 'm-dash 1.6s linear infinite' }}
            />
          )
        return <line key={`e-${i}`} x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke={e.c} strokeWidth="2.6" strokeOpacity="0.85" />
      })}

      {/* center mark */}
      <circle cx={C} cy={C} r={size * 0.03} fill={B.red} />
      <circle cx={C} cy={C} r={size * 0.052} fill="none" stroke={B.red} strokeWidth="1.4" strokeOpacity=".4" />

      {/* nodes + labels */}
      {pts.map((p, i) => {
        const right = Math.cos(p.a) > 0.25
        const left = Math.cos(p.a) < -0.25
        const lx = p.x + (right ? dotR + 14 : left ? -(dotR + 14) : 0)
        const ly = p.y + (Math.abs(Math.cos(p.a)) <= 0.25 ? (Math.sin(p.a) > 0 ? dotR + 30 : -(dotR + 18)) : 0)
        const anchor = right ? 'start' : left ? 'end' : 'middle'
        return (
          <g key={`n-${i}`}>
            <circle
              cx={p.x} cy={p.y} r={dotR}
              fill={p.k === 'r' ? 'url(#fg-red)' : 'url(#fg-grn)'}
              stroke="#fff" strokeWidth="2.5"
              style={i % 3 === 0 ? { animation: `m-pulse ${2.6 + i * 0.2}s ease-in-out infinite` } : undefined}
            />
            <text
              x={lx} y={ly} textAnchor={anchor} dominantBaseline="middle"
              className="m-sans" fontSize={size * 0.0285} fontWeight="600" fill={B.inkSoft}
            >
              {p.t}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export function PosterData({ inviter, code, qrUrl }: PosterProps) {
  const B = BRAND
  const Legend = ({ swatch, dashed, label }: { swatch: string; dashed?: boolean; label: string }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <svg width="42" height="12">
        <line x1="1" y1="6" x2="41" y2="6" stroke={swatch} strokeWidth="3.5" strokeDasharray={dashed ? '4 6' : '0'} strokeLinecap="round" />
      </svg>
      <span className="m-sans" style={{ fontSize: 22, color: B.inkSoft, fontWeight: 500 }}>{label}</span>
    </div>
  )

  return (
    <div className="m-paper" style={{ width: 1080, height: 1920, overflow: 'hidden', position: 'relative', color: B.ink }}>
      {/* ── header ── */}
      <div style={{ padding: '74px 88px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 22 }}>
          <Seal size={84} />
          <div>
            <div className="m-serif" style={{ fontSize: 40, fontWeight: 700, letterSpacing: '.1em', lineHeight: 1.1 }}>
              点金&nbsp;<span style={{ fontWeight: 500 }}>Midas</span>
            </div>
            <div className="m-sans m-tracked-sm" style={{ fontSize: 16, color: B.inkFaint, marginTop: 6 }}>AI 金融分析终端</div>
          </div>
        </div>
        <div style={{ height: 1, background: 'rgba(28,24,21,.14)', marginTop: 30 }} />
      </div>

      {/* ── hero ── */}
      <div style={{ padding: '54px 88px 0', textAlign: 'center' }}>
        <div className="m-sans m-tracked" style={{ fontSize: 18, color: B.red, fontWeight: 600 }}>AI 结构沙盘</div>
        <div className="m-serif" style={{ fontSize: 100, fontWeight: 800, letterSpacing: '.03em', marginTop: 22, lineHeight: 1.1 }}>
          看懂结构<span style={{ color: B.red }}>,</span>再出手
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 18 }}>
          <FactorGraph size={720} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 56, marginTop: 10 }}>
          <Legend swatch={B.red} label="共振" />
          <Legend swatch={B.gold} dashed label="背离" />
        </div>
        <div className="m-serif" style={{ fontSize: 30, fontWeight: 600, color: B.inkSoft, marginTop: 26, letterSpacing: '.08em' }}>
          加密 · 美股 · A 股 · 港股
        </div>
      </div>

      {/* ── action card (China red) ── */}
      <div style={{ position: 'absolute', left: 88, right: 88, bottom: 70, background: B.red, color: '#FBF4E9', boxShadow: '0 24px 60px rgba(150,15,40,.32)' }}>
        <div style={{ padding: '46px 50px 40px', display: 'flex', alignItems: 'center', gap: 40 }}>
          <div style={{ flex: 1 }}>
            <div className="m-sans m-tracked-sm" style={{ fontSize: 17, color: 'rgba(251,244,233,.78)' }}>扫 码 注 册</div>
            <div className="m-serif" style={{ fontSize: 52, fontWeight: 800, lineHeight: 1.22, marginTop: 14 }}>
              双方各得<br /><span style={{ color: '#F4D27A' }}>15 天 Pro</span> 会员
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 30 }}>
              <span className="m-sans" style={{ fontSize: 15, color: 'rgba(251,244,233,.7)', letterSpacing: '.2em' }}>邀请码</span>
              <span className="m-mono" style={{ fontSize: 32, fontWeight: 700, letterSpacing: '.16em', color: '#F4D27A' }}>{code}</span>
            </div>
          </div>
          <div style={{ flexShrink: 0, padding: 16, background: '#FBF4E9' }}>
            <PosterQR url={qrUrl} size={236} dark={B.ink} />
          </div>
        </div>
        <div style={{ borderTop: '1px solid rgba(251,244,233,.22)', padding: '24px 50px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="m-serif" style={{ fontSize: 30, fontWeight: 700 }}>
            <span style={{ color: '#F4D27A' }}>{inviter}</span> 邀请你一起
          </span>
          <span className="m-sans" style={{ fontSize: 16, color: 'rgba(251,244,233,.7)', letterSpacing: '.14em' }}>MIDAS TRADING · CLOUDFLARE</span>
        </div>
      </div>
    </div>
  )
}
