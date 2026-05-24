import type { HTMLAttributes, ReactNode, ThHTMLAttributes, TdHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

/**
 * 统一数据表 recipe(0022 §3.3)· 收口两套表格风格(列表页有外壳 vs account/perp 无外壳)。
 *
 * 标准:overflow-x-auto + rounded-lg + border-paper 外壳 · thead bg-surface-subtle text-xs muted ·
 *   单元格 px-3 py-2(紧凑表 py-1.5)· 行 border-paper/60 + hover:bg-midas-red-glow/30 ·
 *   数字列右对齐 + font-mono tabular-nums · 无斑马纹(沿用)。
 *
 * 用法:<DataTable minWidth="820px"><THead>…</THead><tbody>{rows.map(r=><TRow><TCell>…</TCell></TRow>)}</tbody></DataTable>
 */
export function DataTable({
  minWidth,
  className,
  children,
  ...props
}: HTMLAttributes<HTMLTableElement> & { minWidth?: string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-paper">
      <table
        className={cn('w-full text-sm', className)}
        style={minWidth != null ? { minWidth } : undefined}
        {...props}
      >
        {children}
      </table>
    </div>
  )
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead>
      <tr className="border-b border-paper bg-surface-subtle text-xs text-muted-foreground">
        {children}
      </tr>
    </thead>
  )
}

export function TH({
  align = 'left',
  className,
  children,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement> & { align?: 'left' | 'right' | 'center' }) {
  return (
    <th
      className={cn(
        'px-3 py-2 font-medium',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        className,
      )}
      {...props}
    >
      {children}
    </th>
  )
}

export function TRow({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={cn('border-b border-paper/60', className)} {...props}>
      {children}
    </tr>
  )
}

export function TCell({
  align = 'left',
  mono = false,
  compact = false,
  className,
  children,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement> & {
  align?: 'left' | 'right' | 'center'
  /** 数字列:font-mono + tabular-nums */
  mono?: boolean
  /** 紧凑行高 py-1.5(默认 py-2) */
  compact?: boolean
}) {
  return (
    <td
      className={cn(
        'px-3',
        compact ? 'py-1.5' : 'py-2',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        mono && 'font-mono tabular-nums',
        className,
      )}
      {...props}
    >
      {children}
    </td>
  )
}
