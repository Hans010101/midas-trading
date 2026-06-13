'use client'

/**
 * 邀请海报 · 共享品牌系统(Phase 1.5 刀C · Design 资料包 brand.jsx 移植)。
 *
 * 移植要点(非重写):
 * - window 全局 → TS 模块导出 BRAND / Seal / InkWash;
 * - Seal 接真实官方印章(public/brand/poster/seal.png · dark 版 seal-gold.png),
 *   保留 Design 的 SVG 占位绘制仅作 src 缺失兜底(正常不触发);
 * - m- 作用域类(m-paper/m-serif/m-sans/m-mono/m-tracked/keyframes)一次性注入,
 *   ★ 字体对齐全站 next/font 变量(var(--font-serif/sans/mono)),不在 build 打
 *   Google Fonts;Space Mono → 复用全站 JetBrains Mono(--font-mono);
 * - 海报在 1080×1920 真实坐标空间创作,弹层按比例缩放预览 / 导出。
 *
 * 🔴 设计 token 守全站:中国红 #C8102E / 朱红 #DC143C / 墨绿 #0F6E5F / 帝王金 #B8860B,
 *   不碰缠论淡灰蓝 #6482A0。
 */

import { useId } from 'react'

export const BRAND = {
  red: '#C8102E', // 中国红 — core
  vermilion: '#DC143C', // 朱红
  inkGreen: '#0F6E5F', // 墨绿
  gold: '#B8860B', // 帝王金
  goldSoft: '#C9A14A',
  paper: '#F4EEE2', // 宣纸暖白
  paperDeep: '#EBE2CF',
  ink: '#1C1815', // 墨
  inkSoft: '#5A5046',
  inkFaint: '#8A7F70',
} as const

// 官方印章素材(Design 交付 · 石刻篆印「点金」)· dark 版烫金
export const SEAL_SRC = '/brand/poster/seal.png'
export const SEAL_GOLD_SRC = '/brand/poster/seal-gold.png'

// ── 一次性作用域 CSS(m- 前缀 · 与全站 Tailwind 零冲突)─────────────────────
// 客户端模块加载时注入(海报弹层是 client-only · 无 SSR 首屏依赖)。
// ★ 字体走全站 next/font 变量:CJK 字形随全站走系统 CJK fallback(与全站一致)。
if (typeof document !== 'undefined' && !document.getElementById('midas-poster-css')) {
  const s = document.createElement('style')
  s.id = 'midas-poster-css'
  s.textContent = `
  .m-serif { font-family: var(--font-serif), 'Noto Serif SC', serif; }
  .m-sans  { font-family: var(--font-sans), 'Noto Sans SC', sans-serif; }
  .m-mono  { font-family: var(--font-mono), ui-monospace, monospace; }
  .m-paper {
    background-color: ${BRAND.paper};
    background-image:
      radial-gradient(120% 80% at 20% 0%, rgba(255,255,255,.55) 0%, rgba(255,255,255,0) 55%),
      radial-gradient(120% 90% at 90% 100%, rgba(180,160,120,.12) 0%, rgba(180,160,120,0) 60%);
    position: relative;
  }
  .m-paper::after {
    content: ''; position: absolute; inset: 0; pointer-events: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E");
    mix-blend-mode: multiply; opacity: .05;
  }
  .m-tracked { letter-spacing: .42em; }
  .m-tracked-sm { letter-spacing: .26em; }
  @keyframes m-pulse { 0%,100% { opacity:.35 } 50% { opacity:1 } }
  @keyframes m-dash  { to { stroke-dashoffset: -32 } }
  /* 海报「换个样式」切换淡入(刀C 交互调整) */
  @keyframes poster-fade { from { opacity: .25 } to { opacity: 1 } }
  `
  document.head.appendChild(s)
}

// ── 篆体印章 ── 优先真实 logo(src / SEAL_SRC),缺失才绘制占位(兜底)
interface SealProps {
  size?: number
  chars?: string
  tone?: string
  ink?: string
  distress?: boolean
  style?: React.CSSProperties
  /** 真实印章图;不传默认官方 seal.png(dark 版传 seal-gold.png) */
  src?: string | null
  /** dark 版烫金等 filter */
  filter?: string
}

export function Seal({
  size = 150,
  chars = '点金',
  tone = BRAND.red,
  ink = '#fff',
  distress = true,
  style = {},
  src = SEAL_SRC,
  filter,
}: SealProps) {
  // hooks 必须无条件调用(rules-of-hooks)· 兜底占位用其生成滤镜 id
  const id = useId().replace(/:/g, '')
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- 海报在 1080×1920
      // 真实坐标空间渲染 + html-to-image 导出,需原生 <img>(next/image 优化层
      // 与 foreignObject/canvas 序列化不兼容)
      <img
        src={src}
        alt="点金 Midas 印章"
        width={size}
        height={size}
        style={{ display: 'block', objectFit: 'contain', filter: filter || 'none', ...style }}
      />
    )
  }
  // ── 以下为 src 缺失兜底:Design 的 SVG 占位篆字(正常不触发)──
  const cs = [...chars]
  const grid = cs.length >= 3
  const inset = Math.round(size * 0.085)
  const inner = size - inset * 2
  const order4 = [cs[0], cs[1], cs[2], cs[3]]
  return (
    <div style={{ position: 'relative', width: size, height: size, ...style }}>
      <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
        <filter id={`seal-d-${id}`}>
          <feTurbulence type="fractalNoise" baseFrequency="0.045 0.06" numOctaves="3" seed="7" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale={distress ? 5 : 0} />
        </filter>
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: tone,
          borderRadius: Math.round(size * 0.05),
          filter: distress ? `url(#seal-d-${id})` : 'none',
          boxShadow: `0 ${size * 0.02}px ${size * 0.12}px rgba(140,20,40,.22)`,
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset,
            border: `${Math.max(2, size * 0.022)}px solid ${ink}`,
            borderRadius: Math.round(size * 0.03),
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: inset + Math.round(size * 0.055),
            display: 'grid',
            gridTemplateColumns: grid ? '1fr 1fr' : '1fr',
            gridTemplateRows: grid ? '1fr 1fr' : `repeat(${cs.length}, 1fr)`,
            placeItems: 'center',
          }}
        >
          {(grid ? order4 : cs).map((c, i) => (
            <span
              key={i}
              className="m-serif"
              style={{
                color: ink,
                fontWeight: 900,
                fontSize: grid ? inner * 0.4 : inner * (cs.length === 1 ? 0.72 : 0.46),
                lineHeight: 1,
              }}
            >
              {c}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── 水墨晕染 ── 纯 SVG(离线 · 无图片)
interface InkWashProps {
  id?: string
  color?: string
  style?: React.CSSProperties
  opacity?: number
}

export function InkWash({ id = 'ink', color = BRAND.ink, style = {}, opacity = 0.16 }: InkWashProps) {
  return (
    <svg
      viewBox="0 0 600 800"
      preserveAspectRatio="xMidYMid slice"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', ...style }}
      aria-hidden="true"
    >
      <defs>
        <filter id={`${id}-turb`} x="-30%" y="-30%" width="160%" height="160%">
          <feTurbulence type="fractalNoise" baseFrequency="0.011 0.016" numOctaves="4" seed="23" result="t" />
          <feDisplacementMap in="SourceGraphic" in2="t" scale="120" />
          <feGaussianBlur stdDeviation="7" />
        </filter>
        <radialGradient id={`${id}-g`} cx="50%" cy="45%" r="60%">
          <stop offset="0%" stopColor={color} stopOpacity="0.9" />
          <stop offset="55%" stopColor={color} stopOpacity="0.45" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </radialGradient>
      </defs>
      <g filter={`url(#${id}-turb)`} opacity={opacity}>
        <ellipse cx="300" cy="360" rx="210" ry="240" fill={`url(#${id}-g)`} />
        <ellipse cx="380" cy="250" rx="120" ry="140" fill={`url(#${id}-g)`} opacity="0.7" />
        <ellipse cx="230" cy="470" rx="150" ry="130" fill={`url(#${id}-g)`} opacity="0.8" />
      </g>
    </svg>
  )
}
