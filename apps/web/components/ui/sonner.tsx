'use client'

import {
  CircleCheck,
  Info,
  LoaderCircle,
  OctagonX,
  TriangleAlert,
} from 'lucide-react'
import { Toaster as Sonner } from 'sonner'

type ToasterProps = React.ComponentProps<typeof Sonner>

/**
 * 点金 Midas Toaster · 0008 v2 § 8 决策点 5:
 * 成功 → 帝王金(gold)· 失败 → 中国红 · 绝不绿色(避免跟 K 线涨跌色冲突)。
 *
 * 用 toastOptions.classNames 覆盖默认 success/error 配色,
 * 不用 richColors(richColors 默认 success=lime green)。
 */
const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      // 不传 richColors · 默认中性色,我们用 classNames 自己定 success/error 配色
      className="toaster group"
      icons={{
        success: <CircleCheck className="h-4 w-4" />,
        info: <Info className="h-4 w-4" />,
        warning: <TriangleAlert className="h-4 w-4" />,
        error: <OctagonX className="h-4 w-4" />,
        loading: <LoaderCircle className="h-4 w-4 animate-spin" />,
      }}
      toastOptions={{
        classNames: {
          toast:
            'group toast group-[.toaster]:bg-cream group-[.toaster]:text-foreground group-[.toaster]:border-paper group-[.toaster]:shadow-lg',
          description: 'group-[.toast]:text-muted-foreground',
          // 成功 = 帝王金 border + 帝王金 icon(永不绿色)
          success:
            '!bg-gold/[0.08] !border-gold !text-foreground [&_svg]:!text-gold',
          // 失败 = 中国红 border + 中国红 icon
          error:
            '!bg-midas-red-glow !border-midas-red !text-foreground [&_svg]:!text-midas-red',
          // info / warning 用米色 / 暖警告
          info: '!border-paper [&_svg]:!text-foreground',
          warning:
            '!bg-gold/[0.04] !border-warn [&_svg]:!text-warn',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
