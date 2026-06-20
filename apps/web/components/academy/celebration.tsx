'use client'

/**
 * 结业达标庆祝动画 · 训练营 B 期刀3(★Hans 要的仪式感)。
 *
 * 纯 CSS 纸屑(★不引重型库 · 无 canvas-confetti)· 固定遮罩 + 居中卡片 ·
 * 可关闭(点遮罩 / X / 按钮)· 移动端适配(卡片 max-w + 纸屑覆盖视口)。
 * 纯展示组件 · 数据(标题/副标题)由父组件传 · 独立可复用。
 */

import { Award, X } from 'lucide-react'

const COLORS = ['#C8102E', '#B8860B', '#0F6E5F', '#DC143C', '#F5C518', '#E8A317']
const PIECES = Array.from({ length: 60 }, (_, i) => i)

export function Celebration({
  title,
  subtitle,
  onClose,
}: {
  title: string
  subtitle?: string
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      {/* 纸屑层(纯 CSS · 不拦点击)*/}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        {PIECES.map((i) => {
          // 确定性参数(避免 SSR/hydration 抖动)
          const left = (i * 6.37) % 100
          const delay = (i % 12) * 0.18
          const dur = 2.6 + (i % 5) * 0.4
          const size = 6 + (i % 4) * 2
          return (
            <span
              key={i}
              className="midas-confetti"
              style={{
                left: `${left}%`,
                width: `${size}px`,
                height: `${size * 1.6}px`,
                backgroundColor: COLORS[i % COLORS.length],
                animationDelay: `${delay}s`,
                animationDuration: `${dur}s`,
                borderRadius: i % 2 === 0 ? '2px' : '50%',
              }}
            />
          )
        })}
      </div>

      {/* 庆祝卡片 */}
      <div
        className="relative w-full max-w-sm rounded-2xl border border-gold/40 bg-cream p-6 text-center shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭"
          className="absolute right-3 top-3 text-muted-foreground/60 transition-colors hover:text-foreground"
        >
          <X className="h-5 w-5" />
        </button>
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-gold/15">
          <Award className="h-9 w-9 text-gold" />
        </div>
        <p className="mt-4 font-serif text-lg font-bold text-foreground">{title}</p>
        {subtitle && <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>}
        <button
          type="button"
          onClick={onClose}
          className="mt-5 rounded-lg bg-gold px-5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          知道了
        </button>
      </div>

      {/* 纸屑动画(自包含 · 不污染全局命名)*/}
      <style>{`
        @keyframes midasConfettiFall {
          0%   { transform: translateY(-12vh) rotate(0deg); opacity: 0; }
          10%  { opacity: 1; }
          100% { transform: translateY(105vh) rotate(720deg); opacity: 0.9; }
        }
        .midas-confetti {
          position: absolute;
          top: -5vh;
          animation-name: midasConfettiFall;
          animation-timing-function: linear;
          animation-iteration-count: infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          .midas-confetti { animation: none; display: none; }
        }
      `}</style>
    </div>
  )
}
