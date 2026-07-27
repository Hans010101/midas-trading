'use client'

/** 版四「极简留白」· 奢侈的空(Design poster-minimal.jsx 移植)。1080×1920。 */

import { BRAND, Seal } from '@/components/poster/brand'
import { PosterQR } from '@/components/poster/poster-qr'
import type { PosterProps } from '@/components/poster/types'

export function PosterMinimal({ inviter, code, qrUrl }: PosterProps) {
  const B = BRAND
  return (
    <div
      style={{
        width: 1080, height: 1920, overflow: 'hidden', position: 'relative', background: '#FBFAF6', color: B.ink,
        display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '88px 96px',
      }}
    >
      {/* crest */}
      <div style={{ marginTop: 150 }}>
        <Seal size={128} />
      </div>
      <div className="m-sans" style={{ marginTop: 26, fontSize: 17, color: B.inkFaint, letterSpacing: '.46em', paddingLeft: '.46em' }}>点金 MIDAS</div>

      {/* single serif headline */}
      <div style={{ marginTop: 132, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <span style={{ width: 56, height: 2, background: B.red }} />
        <div className="m-serif" style={{ fontSize: 138, fontWeight: 800, letterSpacing: '.12em', paddingLeft: '.12em', marginTop: 48, lineHeight: 1 }}>点石成金</div>
        <div className="m-serif" style={{ fontSize: 26, fontWeight: 400, color: B.inkSoft, letterSpacing: '.24em', paddingLeft: '.24em', marginTop: 44, whiteSpace: 'nowrap' }}>以虚拟资金 · 磨真功夫</div>
      </div>

      <div style={{ flex: 1 }} />

      {/* refined QR */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div style={{ padding: 20, background: '#fff', boxShadow: '0 10px 36px rgba(0,0,0,.08)' }}>
          <PosterQR url={qrUrl} size={244} dark={B.ink} />
        </div>
        <div className="m-sans" style={{ marginTop: 24, fontSize: 22, fontWeight: 700, letterSpacing: '.18em', paddingLeft: '.18em', color: B.red, whiteSpace: 'nowrap' }}>扫 码 注 册</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 16 }}>
          <span className="m-sans" style={{ fontSize: 15, color: B.inkFaint, letterSpacing: '.2em' }}>邀请码</span>
          <span className="m-mono" style={{ fontSize: 27, fontWeight: 700, letterSpacing: '.16em', color: B.ink }}>{code}</span>
        </div>
      </div>

      {/* whisper-quiet 落款 + reward */}
      <div style={{ marginTop: 46, textAlign: 'center' }}>
        <div className="m-serif" style={{ fontSize: 27, fontWeight: 600 }}>
          <span style={{ color: B.red }}>{inviter}</span> 邀请你一起 · 各得 15 天 Pro
        </div>
        <div className="m-sans" style={{ marginTop: 14, fontSize: 14, color: B.inkFaint, letterSpacing: '.18em' }}>MIDAS TRADING · CLOUDFLARE</div>
      </div>
    </div>
  )
}
