'use client'

/** 版三「水墨意境」· 最艺术,超大印章 + 竖排(Design poster-ink.jsx 移植)。1080×1920。 */

import { BRAND, InkWash, Seal } from '@/components/poster/brand'
import { PosterQR } from '@/components/poster/poster-qr'
import type { PosterProps } from '@/components/poster/types'

export function PosterInk({ inviter, code, qrUrl }: PosterProps) {
  const B = BRAND
  return (
    <div className="m-paper" style={{ width: 1080, height: 1920, overflow: 'hidden', position: 'relative', color: B.ink }}>
      <InkWash id="ink-a" color={B.ink} opacity={0.14} style={{ top: '-26%', left: '18%', transform: 'scale(1.25)' }} />
      <InkWash id="ink-b" color={B.ink} opacity={0.07} style={{ top: '34%', left: '-32%', transform: 'scale(1.05) rotate(8deg)' }} />

      {/* top-left wordmark */}
      <div style={{ position: 'absolute', top: 84, left: 96 }}>
        <div className="m-serif" style={{ fontSize: 34, fontWeight: 700, letterSpacing: '.12em' }}>点金&nbsp;<span style={{ fontWeight: 500 }}>Midas</span></div>
        <div className="m-sans m-tracked-sm" style={{ fontSize: 14, color: B.inkFaint, marginTop: 7 }}>AI 金融分析终端</div>
      </div>

      {/* oversized brand seal — stamped, slightly askew */}
      <div style={{ position: 'absolute', top: 232, right: 132, transform: 'rotate(-3.5deg)' }}>
        <Seal size={332} />
      </div>

      {/* vertical headline column */}
      <div style={{ position: 'absolute', top: 600, right: 150, writingMode: 'vertical-rl', textOrientation: 'upright' }}>
        <span className="m-serif" style={{ fontSize: 168, fontWeight: 800, letterSpacing: '.06em', lineHeight: 1.04, color: B.ink }}>点石成金</span>
      </div>

      {/* secondary phrase */}
      <div style={{ position: 'absolute', top: 660, right: 372, writingMode: 'vertical-rl', textOrientation: 'upright' }}>
        <span className="m-serif" style={{ fontSize: 46, fontWeight: 500, letterSpacing: '.22em', lineHeight: 1.6, color: B.inkSoft }}>以虚拟资金,磨真功夫</span>
      </div>

      {/* bottom-left action block */}
      <div style={{ position: 'absolute', left: 88, bottom: 96, width: 496, border: `1.5px solid ${B.red}`, background: 'rgba(244,238,226,.82)', backdropFilter: 'blur(2px)', padding: '34px 36px 30px', boxShadow: '0 14px 40px rgba(120,20,40,.12)' }}>
        <div className="m-serif" style={{ fontSize: 32, fontWeight: 800 }}>
          诚邀同行<span style={{ color: B.red }}>,</span>各得&nbsp;<span style={{ color: B.red }}>15 天 Pro</span>
        </div>
        <div style={{ display: 'flex', gap: 26, marginTop: 26, alignItems: 'center' }}>
          <div style={{ padding: 14, background: '#fff', border: '1px solid rgba(28,24,21,.1)', flexShrink: 0, boxShadow: '0 4px 16px rgba(0,0,0,.07)' }}>
            <PosterQR url={qrUrl} size={196} dark={B.ink} />
          </div>
          <div>
            <div className="m-sans" style={{ fontSize: 21, fontWeight: 700, letterSpacing: '.06em', color: B.red, lineHeight: 1.35 }}>扫码<br />注册</div>
            <div className="m-sans" style={{ fontSize: 14, color: B.inkFaint, letterSpacing: '.2em', marginTop: 22 }}>邀请码</div>
            <div className="m-mono" style={{ fontSize: 26, fontWeight: 700, letterSpacing: '.1em', color: B.ink, marginTop: 6 }}>{code}</div>
          </div>
        </div>
        <div style={{ height: 1, background: 'rgba(200,16,46,.28)', margin: '24px 0 18px' }} />
        <div className="m-serif" style={{ fontSize: 25, fontWeight: 700 }}>
          <span style={{ color: B.red }}>{inviter}</span> 邀请你一起
        </div>
      </div>
    </div>
  )
}
