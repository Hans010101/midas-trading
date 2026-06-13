'use client'

/** 版五「深色高级 · 夜间终端」· 唯一深色版(Design poster-dark.jsx 移植)。1080×1920。
 *  ★ 印章用烫金 seal-gold.png(Design 钩子)。 */

import { BRAND, SEAL_GOLD_SRC, Seal } from '@/components/poster/brand'
import { PosterQR } from '@/components/poster/poster-qr'
import type { PosterProps } from '@/components/poster/types'

export function PosterDark({ inviter, code, qrUrl }: PosterProps) {
  const B = BRAND
  const BG = '#16130F' // warm near-black
  const GOLD = '#D9B45A' // legible gold for type on dark
  const GOLD_DIM = '#9C8246'
  const goldGrad = `linear-gradient(135deg, #E9CE84 0%, ${B.gold} 55%, #8C661A 100%)`

  const Radar = () => (
    <svg viewBox="0 0 600 600" style={{ position: 'absolute', top: 560, left: '50%', width: 760, transform: 'translateX(-50%)', opacity: 0.5 }} aria-hidden="true">
      {[90, 170, 250].map((r, i) => (
        <circle key={i} cx="300" cy="300" r={r} fill="none" stroke={GOLD} strokeOpacity="0.14" strokeWidth="1" />
      ))}
      {Array.from({ length: 12 }).map((_, i) => {
        const a = (i / 12) * Math.PI * 2
        return <line key={i} x1="300" y1="300" x2={300 + 250 * Math.cos(a)} y2={300 + 250 * Math.sin(a)} stroke={GOLD} strokeOpacity="0.07" strokeWidth="1" />
      })}
    </svg>
  )

  return (
    <div style={{ width: 1080, height: 1920, overflow: 'hidden', position: 'relative', background: BG, color: GOLD, display: 'flex', flexDirection: 'column', padding: '88px 96px' }}>
      <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(110% 70% at 50% 30%, rgba(217,180,90,.07) 0%, rgba(217,180,90,0) 60%)' }} />
      <Radar />

      {/* header */}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 24 }}>
        <Seal size={96} src={SEAL_GOLD_SRC} />
        <div>
          <div className="m-serif" style={{ fontSize: 42, fontWeight: 700, letterSpacing: '.1em', background: goldGrad, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>点金&nbsp;Midas</div>
          <div className="m-sans m-tracked-sm" style={{ fontSize: 15, color: GOLD_DIM, marginTop: 7 }}>AI 金融分析终端</div>
        </div>
      </div>
      <div style={{ position: 'relative', height: 1, background: `linear-gradient(90deg, ${B.gold}, transparent)`, marginTop: 30, opacity: 0.55 }} />

      {/* headline */}
      <div style={{ position: 'relative', marginTop: 150, textAlign: 'center' }}>
        <div className="m-sans m-tracked" style={{ fontSize: 18, color: GOLD_DIM, fontWeight: 500 }}>四 市 通 览</div>
        <div className="m-serif" style={{ fontSize: 168, fontWeight: 800, letterSpacing: '.06em', paddingLeft: '.06em', marginTop: 30, lineHeight: 1.05, background: goldGrad, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>点石成金</div>
        <div className="m-serif" style={{ fontSize: 27, fontWeight: 400, color: '#C9BBA0', letterSpacing: '.12em', marginTop: 38 }}>
          AI 结构沙盘 · 虚拟实战 · <span style={{ color: GOLD }}>零风险</span>
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {/* action — red reward strip + cream QR */}
      <div style={{ position: 'relative', border: '1px solid rgba(217,180,90,.35)', padding: '40px 44px 38px', background: 'rgba(217,180,90,.04)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 38 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'inline-block', background: B.red, color: '#FBF4E9', padding: '10px 22px', borderRadius: 2 }}>
              <span className="m-sans" style={{ fontSize: 19, fontWeight: 700, letterSpacing: '.08em' }}>限时邀请有礼</span>
            </div>
            <div className="m-serif" style={{ fontSize: 50, fontWeight: 800, lineHeight: 1.22, marginTop: 22, color: '#F1E6CC' }}>
              双方各得<br /><span style={{ background: goldGrad, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>15 天 Pro</span> 会员
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 28 }}>
              <span className="m-sans" style={{ fontSize: 15, color: GOLD_DIM, letterSpacing: '.2em' }}>邀请码</span>
              <span className="m-mono" style={{ fontSize: 30, fontWeight: 700, letterSpacing: '.16em', color: GOLD }}>{code}</span>
            </div>
          </div>
          <div style={{ flexShrink: 0, padding: 16, background: '#F4EEDF' }}>
            <PosterQR url={qrUrl} size={228} dark={BG} />
            <div className="m-sans" style={{ textAlign: 'center', marginTop: 12, fontSize: 18, fontWeight: 700, letterSpacing: '.16em', paddingLeft: '.16em', color: B.red }}>扫码注册</div>
          </div>
        </div>
        <div style={{ borderTop: '1px solid rgba(217,180,90,.22)', marginTop: 30, paddingTop: 22 }}>
          <span className="m-serif" style={{ fontSize: 28, fontWeight: 700, color: '#F1E6CC' }}>
            <span style={{ color: GOLD }}>{inviter}</span> 邀请你一起
          </span>
        </div>
      </div>
    </div>
  )
}
