'use client'

/** 版一「邀请函」· 最克制,如请柬(Design poster-invite.jsx 移植)。1080×1920。 */

import { BRAND, InkWash, Seal } from '@/components/poster/brand'
import { PosterQR } from '@/components/poster/poster-qr'
import type { PosterProps } from '@/components/poster/types'

export function PosterInvite({ inviter, code, qrUrl }: PosterProps) {
  const B = BRAND
  const Corner = ({ pos }: { pos: 'tl' | 'tr' | 'bl' | 'br' }) => {
    const t = 2
    const map = {
      tl: { top: -1, left: -1, bt: t, bl: t },
      tr: { top: -1, right: -1, bt: t, br: t },
      bl: { bottom: -1, left: -1, bb: t, bl: t },
      br: { bottom: -1, right: -1, bb: t, br: t },
    }[pos] as { top?: number; bottom?: number; left?: number; right?: number; bt?: number; bb?: number; bl?: number; br?: number }
    return (
      <div
        style={{
          position: 'absolute', width: 26, height: 26,
          top: map.top, bottom: map.bottom, left: map.left, right: map.right,
          borderTop: map.bt ? `${t}px solid ${B.red}` : 'none',
          borderBottom: map.bb ? `${t}px solid ${B.red}` : 'none',
          borderLeft: map.bl ? `${t}px solid ${B.red}` : 'none',
          borderRight: map.br ? `${t}px solid ${B.red}` : 'none',
        }}
      />
    )
  }

  return (
    <div className="m-paper" style={{ width: 1080, height: 1920, overflow: 'hidden', position: 'relative', color: B.ink }}>
      <InkWash id="inv-ink" color={B.red} opacity={0.05} style={{ top: '-22%', left: '-20%', transform: 'scale(1.1)' }} />

      {/* double-rule invitation border */}
      <div style={{ position: 'absolute', inset: 54, border: `1.5px solid ${B.red}` }} />
      <div style={{ position: 'absolute', inset: 64, border: '1px solid rgba(200,16,46,0.45)' }} />

      <div style={{ position: 'absolute', inset: 64, padding: '96px 104px 80px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {/* ── crest ── */}
        <Seal size={118} />
        <div className="m-serif" style={{ marginTop: 30, fontSize: 46, fontWeight: 700, letterSpacing: '.14em' }}>
          点金&nbsp;<span style={{ fontWeight: 500 }}>Midas</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 22, whiteSpace: 'nowrap' }}>
          <span style={{ width: 46, height: 1, background: 'rgba(28,24,21,.3)' }} />
          <span className="m-sans" style={{ fontSize: 17, color: B.inkSoft, letterSpacing: '.26em', paddingLeft: '.26em' }}>诚挚相邀</span>
          <span style={{ width: 46, height: 1, background: 'rgba(28,24,21,.3)' }} />
        </div>

        {/* ── headline ── */}
        <div style={{ marginTop: 68, textAlign: 'center' }}>
          <div className="m-serif" style={{ fontSize: 104, fontWeight: 800, lineHeight: 1.18, letterSpacing: '.04em' }}>四市通览</div>
          <div style={{ display: 'flex', justifyContent: 'center', margin: '18px 0' }}>
            <span style={{ width: 9, height: 9, background: B.gold, transform: 'rotate(45deg)' }} />
          </div>
          <div className="m-serif" style={{ fontSize: 104, fontWeight: 800, lineHeight: 1.18, letterSpacing: '.04em', color: B.red }}>点石成金</div>
        </div>
        <div className="m-sans m-tracked-sm" style={{ marginTop: 40, fontSize: 21, color: B.inkSoft }}>
          AI&nbsp;结构沙盘 · 虚拟实战 · 零风险
        </div>

        <div style={{ flex: 1 }} />

        {/* ── action box ── */}
        <div style={{ position: 'relative', width: '100%', border: `1.5px solid ${B.red}`, padding: '46px 56px 44px' }}>
          <Corner pos="tl" /><Corner pos="tr" /><Corner pos="bl" /><Corner pos="br" />
          <div className="m-sans m-tracked-sm" style={{ textAlign: 'center', fontSize: 17, color: B.red }}>诚 挚 之 礼</div>
          <div className="m-serif" style={{ textAlign: 'center', fontSize: 50, fontWeight: 800, letterSpacing: '.02em', marginTop: 12, lineHeight: 1.2 }}>
            双方各得&nbsp;<span style={{ color: B.red }}>15 天 Pro</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 20, margin: '32px auto 28px', width: 'fit-content' }}>
            <span style={{ width: 70, height: 1, background: 'rgba(200,16,46,.3)' }} />
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: B.red }} />
            <span style={{ width: 70, height: 1, background: 'rgba(200,16,46,.3)' }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <div style={{ padding: 18, background: '#fff', border: '1px solid rgba(28,24,21,.1)', boxShadow: '0 6px 22px rgba(0,0,0,.08)' }}>
              <PosterQR url={qrUrl} size={272} dark={B.ink} />
            </div>
            <div className="m-sans" style={{ marginTop: 22, fontSize: 24, fontWeight: 700, letterSpacing: '.14em', color: B.red }}>扫码注册 · 即刻同行</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 18 }}>
              <span className="m-sans" style={{ fontSize: 16, color: B.inkFaint, letterSpacing: '.2em' }}>邀请码</span>
              <span className="m-mono" style={{ fontSize: 30, fontWeight: 700, letterSpacing: '.16em', color: B.ink }}>{code}</span>
            </div>
          </div>
        </div>

        {/* ── 落款 ── */}
        <div style={{ marginTop: 40, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 18, whiteSpace: 'nowrap' }}>
            <span style={{ width: 40, height: 1, background: 'rgba(28,24,21,.25)' }} />
            <span className="m-serif" style={{ fontSize: 32, fontWeight: 700 }}>
              <span style={{ color: B.red }}>{inviter}</span> 邀请你一起
            </span>
            <span style={{ width: 40, height: 1, background: 'rgba(28,24,21,.25)' }} />
          </div>
          <div className="m-sans" style={{ marginTop: 14, fontSize: 15, color: B.inkFaint, letterSpacing: '.16em' }}>MIDAS TRADING · CLOUDFLARE</div>
        </div>
      </div>
    </div>
  )
}
