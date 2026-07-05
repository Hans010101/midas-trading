'use client'

/**
 * 设置页 · 做T信号偏好(暗发布开关)· 读写 #158 后端 User.indicator_prefs.day_trade。
 *
 * 开启后:加密市场页出现「做T信号」榜单(读现有 /crypto/boll-scan 只读快照 · 布林结构扫描)。
 * ★暗发布:默认 OFF(进阶功能 · 用户显式开启才可见)· 结构描述非建议,红线免责由榜单内部展示。
 * ★本 section 只暴露 day_trade 单开关(布林/缠论详情页图层偏好在「详情页默认显示」section,
 *   走 cookie · 各管各的 · 不在此重复),避免用户在两处看到同名开关而困惑。
 */

import { useSession } from 'next-auth/react'
import { toast } from 'sonner'

import { useIndicatorPrefs, useSaveIndicatorPrefs } from '@/hooks/use-indicator-prefs'
import { cn } from '@/lib/utils'

export function DayTradeSection() {
  const { status } = useSession()
  const authed = status === 'authenticated'
  const { data, isLoading } = useIndicatorPrefs()
  const save = useSaveIndicatorPrefs()

  const on = data?.day_trade ?? false

  function handleToggle() {
    const next = !on
    save.mutate(
      { day_trade: next },
      {
        onSuccess: () => toast.success(next ? '已开启做T信号' : '已关闭做T信号'),
        onError: (e) => toast.error(e instanceof Error ? e.message : '保存失败'),
      },
    )
  }

  return (
    <section className="mb-6 rounded-lg border border-paper bg-surface-card p-5">
      <h2 className="mb-1 font-serif text-lg font-bold text-foreground">做T信号</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        开启后,加密市场页会出现「做T信号」榜单(布林结构扫描 · 结构描述非建议 · 仅供参考,不构成投资建议)
      </p>

      <div className="flex items-center justify-between gap-3 rounded-md border border-paper bg-background px-3 py-2.5">
        <div className="flex flex-col">
          <span className="text-sm font-medium text-foreground">做T信号榜单</span>
          <span className="text-[11px] text-muted-foreground/60">
            进阶功能 · 默认关闭 · 仅展示布林结构倾向(偏多/偏空/中性)
          </span>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-label="做T信号榜单"
          disabled={!authed || isLoading || save.isPending}
          onClick={handleToggle}
          className={cn(
            'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors',
            on ? 'bg-midas-red' : 'bg-muted',
            (!authed || isLoading || save.isPending) && 'cursor-not-allowed opacity-60',
          )}
        >
          <span
            className={cn(
              'inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform',
              on ? 'translate-x-5' : 'translate-x-0.5',
            )}
          />
        </button>
      </div>

      <p className="mt-4 text-[11px] text-muted-foreground/60">
        偏好按账号保存(跨设备同步)· 做T信号仅为布林通道结构的客观描述,不构成任何买卖建议
      </p>
    </section>
  )
}
