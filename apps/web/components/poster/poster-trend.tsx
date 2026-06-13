'use client'

/** 版六「国潮现代」· 大色块 / 倾斜印章 / 错位字(Design poster-trend.jsx 移植)。1080×1920。 */

import { BRAND, Seal } from '@/components/poster/brand'
import { PosterQR } from '@/components/poster/poster-qr'
import type { PosterProps } from '@/components/poster/types'

export function PosterTrend({ inviter, code, qrUrl }: PosterProps) {
  const B = BRAND
  return (
    <div className="m-paper" style={{ width: 1080, height: 1920, overflow: 'hidden', position: 'relative', color: B.ink }}>
      {/* ── top red field ── */}
      <div style={{ position: 'absolute', top: 0, left: 0, width: 1080, height: 560, background: B.red, overflow: 'hidden' }}>
        <svg width="1080" height="560" style={{ position: 'absolute', inset: 0, opacity: 0.5 }} aria-hidden="true">
          <line x1="640" y1="-40" x2="1180" y2="500" stroke={B.gold} strokeWidth="2" />
          <line x1="720" y1="-40" x2="1260" y2="500" stroke={B.gold} strokeWidth="2" />
        </svg>
        <div style={{ position: 'absolute', top: 76, left: 88 }}>
          <div className="m-serif" style={{ fontSize: 34, fontWeight: 700, letterSpacing: '.1em', color: '#F4D27A' }}>点金&nbsp;Midas</div>
          <div className="m-sans m-tracked-sm" style={{ fontSize: 14, color: 'rgba(251,244,233,.78)', marginTop: 7 }}>AI 金融分析终端 · 四市通览</div>
        </div>
        <div className="m-serif" style={{ position: 'absolute', left: 80, top: 210, fontSize: 230, fontWeight: 900, color: '#FBF4E9', lineHeight: 0.92, letterSpacing: '.02em' }}>点石</div>
      </div>

      {/* tilted seal on white plate, straddling the boundary */}
      <div style={{ position: 'absolute', top: 430, right: 96, transform: 'rotate(-8deg)', padding: 18, background: '#FBFAF6', boxShadow: '0 16px 40px rgba(0,0,0,.18)' }}>
        <Seal size={150} />
      </div>

      {/* ── staggered title — second pair on paper ── */}
      <div className="m-serif" style={{ position: 'absolute', left: 360, top: 600, fontSize: 230, fontWeight: 900, color: B.red, lineHeight: 0.92, letterSpacing: '.02em' }}>成金</div>

      {/* accents */}
      <div style={{ position: 'absolute', left: 364, top: 850, width: 312, height: 16, background: B.inkGreen }} />
      <div style={{ position: 'absolute', left: 130, top: 700, width: 40, height: 40, background: B.gold, transform: 'rotate(45deg)' }} />
      <div style={{ position: 'absolute', left: 150, top: 920, width: 84, height: 84, border: `5px solid ${B.inkGreen}`, borderRadius: '50%' }} />

      {/* slogan */}
      <div style={{ position: 'absolute', left: 88, top: 1010, display: 'flex', alignItems: 'center', gap: 18 }}>
        <span style={{ width: 14, height: 44, background: B.red }} />
        <span className="m-serif" style={{ fontSize: 52, fontWeight: 800, letterSpacing: '.04em' }}>看懂结构<span style={{ color: B.red }}>,</span>再出手</span>
      </div>
      <div className="m-sans" style={{ position: 'absolute', left: 122, top: 1086, fontSize: 22, color: B.inkSoft, letterSpacing: '.06em' }}>
        AI 结构沙盘 · 虚拟实战 · 零风险
      </div>

      {/* ── bottom action card ── */}
      <div style={{ position: 'absolute', left: 88, right: 88, bottom: 96, background: '#FBFAF6', boxShadow: '0 20px 50px rgba(0,0,0,.12)' }}>
        <div style={{ background: B.red, color: '#FBF4E9', padding: '20px 36px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="m-serif" style={{ fontSize: 36, fontWeight: 800 }}>双方各得 <span style={{ color: '#F4D27A' }}>15 天 Pro</span></span>
          <span className="m-sans m-tracked-sm" style={{ fontSize: 16, color: 'rgba(251,244,233,.8)' }}>邀请有礼</span>
        </div>
        <div style={{ padding: '34px 36px 30px', display: 'flex', alignItems: 'center', gap: 34 }}>
          <div style={{ flexShrink: 0, padding: 14, background: '#fff', border: '1px solid rgba(28,24,21,.1)' }}>
            <PosterQR url={qrUrl} size={210} dark={B.ink} />
          </div>
          <div style={{ flex: 1 }}>
            <div className="m-sans" style={{ fontSize: 26, fontWeight: 800, letterSpacing: '.08em', color: B.red }}>扫码注册</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 18 }}>
              <span className="m-sans" style={{ fontSize: 15, color: B.inkFaint, letterSpacing: '.2em' }}>邀请码</span>
              <span className="m-mono" style={{ fontSize: 28, fontWeight: 700, letterSpacing: '.12em', color: B.ink }}>{code}</span>
            </div>
            <div style={{ height: 1, background: 'rgba(28,24,21,.12)', margin: '22px 0 18px' }} />
            <div className="m-serif" style={{ fontSize: 27, fontWeight: 700 }}>
              <span style={{ color: B.red }}>{inviter}</span> 邀请你一起
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
