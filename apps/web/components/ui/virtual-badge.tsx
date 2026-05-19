import { cn } from '@/lib/utils'

type Size = 'sm' | 'md' | 'lg'

interface VirtualBadgeProps {
  size?: Size
  className?: string
}

/**
 * 帝王金徽章 · 所有虚拟交易元素必带
 * 04 文档 Task 7.4 标准实现
 */
export function VirtualBadge({ size = 'md', className }: VirtualBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center font-mono tracking-wider',
        'bg-gold/[0.08] border border-gold/40 text-gold rounded-full',
        size === 'sm' && 'text-[10px] px-2 py-0.5',
        size === 'md' && 'text-xs px-2.5 py-1',
        size === 'lg' && 'text-sm px-3 py-1.5',
        className,
      )}
    >
      VIRTUAL · 模拟
    </span>
  )
}
