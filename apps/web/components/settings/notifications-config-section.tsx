'use client'

/**
 * 设置页 · 消息推送配置 section · 0025 G2a 统一 Telegram bot。
 *
 * 0025 改动:移除飞书 + per-user TG token 手填;Telegram 经统一 bot 的 /start 绑定。
 * 本期(G2a)只展示绑定状态 + 测试按钮 + 事件总开关;完整绑定 UX(扫码 / deep link)
 * 在 G5 接入。Toast 配色:成功帝王金,失败中国红,绝不绿色。
 */

import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  useNotificationConfig,
  useSaveNotificationConfig,
  useSendTestNotification,
} from '@/hooks/use-notifications'
import { cn } from '@/lib/utils'

export function NotificationsConfigSection() {
  const { data: config, isLoading } = useNotificationConfig()
  const saveMutation = useSaveNotificationConfig()

  const [tradeEnabled, setTradeEnabled] = useState(true)
  const [priceEnabled, setPriceEnabled] = useState(true)

  useEffect(() => {
    if (config) {
      setTradeEnabled(config.trade_alert_enabled)
      setPriceEnabled(config.price_alert_enabled)
    }
  }, [config])

  async function saveSwitches() {
    try {
      await saveMutation.mutateAsync({
        trade_alert_enabled: tradeEnabled,
        price_alert_enabled: priceEnabled,
      })
      toast.success('推送开关已保存')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    }
  }

  if (isLoading) {
    return <p className="py-4 text-sm text-muted-foreground">载入中…</p>
  }

  const bound = config?.has_telegram ?? false

  return (
    <section className="mb-10">
      <h2 className="mb-2 font-serif text-xl font-bold text-foreground">
        消息推送
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">
        绑定 Telegram 后,成交通知 / 价格异动会推送到你的 Telegram · 未绑定只有站内提示
      </p>

      <div className="space-y-4">
        {/* Telegram 绑定状态 */}
        <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
          <div className="mb-3 flex items-center gap-2">
            <span className="text-xl" aria-hidden="true">✈️</span>
            <h3 className="font-serif text-base font-bold text-foreground">
              Telegram
            </h3>
            <span
              className={cn(
                'rounded border px-1.5 py-0.5 font-mono text-[10px]',
                bound
                  ? 'border-gold bg-gold/[0.08] text-gold'
                  : 'border-paper text-muted-foreground/70',
              )}
            >
              {bound ? '✓ 已绑定' : '未绑定'}
            </span>
          </div>
          <p className="mb-3 text-xs text-muted-foreground">
            {bound
              ? '已绑定到你的 Telegram · 推送将发到这里。'
              : '绑定入口即将上线 —— 届时在此扫码 / 点链接,在官方 bot 里 /start 完成绑定。'}
          </p>
          <TestButton disabled={!bound} />
        </div>

        {/* 事件总开关 */}
        <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
          <h3 className="mb-3 font-serif text-base font-bold text-foreground">
            事件总开关
          </h3>
          <div className="mb-3 space-y-2">
            <Toggle
              label="成交通知"
              hint="下单成交后推送"
              checked={tradeEnabled}
              onChange={setTradeEnabled}
            />
            <Toggle
              label="价格异动通知"
              hint="自选股 ±5% · 5 分钟同标的去重"
              checked={priceEnabled}
              onChange={setPriceEnabled}
            />
          </div>
          <SaveButton onClick={saveSwitches} pending={saveMutation.isPending}>
            保存开关
          </SaveButton>
        </div>
      </div>
    </section>
  )
}

// ===== sub-components =====

interface SaveButtonProps {
  onClick: () => void
  pending: boolean
  children: React.ReactNode
}

function SaveButton({ onClick, pending, children }: SaveButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending}
      className="inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:cursor-not-allowed disabled:opacity-50"
    >
      {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </button>
  )
}

function TestButton({ disabled }: { disabled: boolean }) {
  const testMutation = useSendTestNotification()

  async function handleClick() {
    try {
      const result = await testMutation.mutateAsync('telegram')
      if (result.ok) {
        toast.success('Telegram 测试消息已发送')
      } else {
        toast.error(`推送失败 · ${result.error ?? '未知原因'}`)
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '请求失败')
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || testMutation.isPending}
      title={disabled ? '绑定 Telegram 后可用' : undefined}
      className="inline-flex items-center gap-1.5 rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground transition-colors hover:bg-cream disabled:cursor-not-allowed disabled:opacity-50"
    >
      {testMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      发送测试
    </button>
  )
}

interface ToggleProps {
  label: string
  hint: string
  checked: boolean
  onChange: (next: boolean) => void
}

function Toggle({ label, hint, checked, onChange }: ToggleProps) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 rounded-md border border-paper bg-background px-3 py-2 hover:bg-cream">
      <div className="flex-1">
        <div className="text-sm text-foreground">{label}</div>
        <div className="text-xs text-muted-foreground/70">{hint}</div>
      </div>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-midas-red"
      />
      <span
        className={cn(
          'font-mono text-[10px]',
          checked ? 'text-midas-red' : 'text-muted-foreground/50',
        )}
      >
        {checked ? '开' : '关'}
      </span>
    </label>
  )
}
