'use client'

import { type ReactNode } from 'react'

/**
 * D 系列交互组件统一外壳:暖米白卡片 + 衬线标题 + 红竖标 + 统一免责小字。
 * ⛔ 教学页面不挂 VIRTUAL 徽章(红线);用「互动演示」标签区分。
 */
export function InteractiveCard({
  title,
  subtitle,
  children,
  footnote,
}: {
  title: string
  subtitle?: string
  children: ReactNode
  footnote?: string
}) {
  return (
    <figure className="my-8 overflow-hidden rounded-lg border border-paper bg-surface-card shadow-sm">
      <figcaption className="border-b border-paper bg-surface-subtle/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-block h-3.5 w-1 rounded-sm bg-midas-red" aria-hidden />
          <span className="font-serif text-base font-bold text-foreground">{title}</span>
          <span className="ml-auto shrink-0 rounded bg-gold/15 px-1.5 py-0.5 text-[10px] font-medium text-gold">
            互动演示
          </span>
        </div>
        {subtitle ? (
          <p className="mt-1.5 text-xs leading-relaxed text-foreground/60">{subtitle}</p>
        ) : null}
      </figcaption>
      <div className="px-3 py-4 sm:px-4">{children}</div>
      <p className="border-t border-paper px-4 py-2 text-[11px] leading-relaxed text-foreground/50">
        {footnote ?? '示意演示 · 数据为教学示例'}
      </p>
    </figure>
  )
}
