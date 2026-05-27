'use client'

/**
 * 设置页 · 消息推送配置 section · 0025 G2a 统一 Telegram bot。
 *
 * 0025 改动:移除飞书 + per-user TG token 手填;Telegram 经统一 bot 的 /start 绑定。
 * 本期(G2a)只展示绑定状态 + 测试按钮 + 事件总开关;完整绑定 UX(扫码 / deep link)
 * 在 G5 接入。Toast 配色:成功帝王金,失败中国红,绝不绿色。
 */

import { useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  NOTIFICATIONS_KEY,
  useNotificationConfig,
  useSaveNotificationConfig,
  useSendTestNotification,
} from '@/hooks/use-notifications'
import { useCreateBindToken, useUnbindTelegram } from '@/hooks/use-telegram'
import { type BindTokenResult, TelegramApiError } from '@/lib/api/telegram'
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
        {/* Telegram 绑定(G3 · deep link + 二维码 + 解绑 + 重绑提示)*/}
        <TelegramCard bound={bound} />

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

// ===== Telegram 绑定卡 =====

function TelegramCard({ bound }: { bound: boolean }) {
  const createToken = useCreateBindToken()
  const unbind = useUnbindTelegram()
  const queryClient = useQueryClient()
  const [bindInfo, setBindInfo] = useState<BindTokenResult | null>(null)
  const [botUnavailable, setBotUnavailable] = useState(false)

  async function handleBind() {
    setBotUnavailable(false)
    try {
      setBindInfo(await createToken.mutateAsync())
    } catch (e) {
      if (e instanceof TelegramApiError && e.status === 503) {
        setBotUnavailable(true)
      } else {
        toast.error(e instanceof Error ? e.message : '生成绑定链接失败')
      }
    }
  }

  async function handleUnbind() {
    try {
      await unbind.mutateAsync()
      setBindInfo(null)
      toast.success('已解绑 Telegram')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '解绑失败')
    }
  }

  function handleRefresh() {
    void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY.config })
  }

  return (
    <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-xl" aria-hidden="true">✈️</span>
        <h3 className="font-serif text-base font-bold text-foreground">Telegram</h3>
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

      {bound ? (
        <>
          <p className="mb-3 text-xs text-muted-foreground">
            已绑定到你的 Telegram · 成交 / 价格异动 / 告警会推送到这里。
          </p>
          <div className="flex flex-wrap gap-2">
            <TestButton disabled={false} />
            <button
              type="button"
              onClick={handleUnbind}
              disabled={unbind.isPending}
              className="inline-flex items-center gap-1.5 rounded-md border border-midas-red/40 bg-background px-4 py-2 text-sm text-midas-red transition-colors hover:bg-midas-red/[0.06] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {unbind.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              解绑
            </button>
          </div>
        </>
      ) : (
        <>
          {/* D3 重绑提示 · 帝王金强调(G2a 已清空旧 chat_id,存量绑定失效)*/}
          <div className="mb-3 rounded-md border border-gold/40 bg-gold/[0.06] px-3 py-2 text-xs text-foreground">
            <span className="font-medium text-gold">请绑定 / 重新绑定 Telegram</span>
            <br />
            推送已升级为统一官方 bot。若你此前绑定过,旧绑定已失效,请重新绑定;首次使用直接绑定即可。
          </div>

          {!bindInfo && !botUnavailable && (
            <button
              type="button"
              onClick={handleBind}
              disabled={createToken.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:cursor-not-allowed disabled:opacity-50"
            >
              {createToken.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              绑定 Telegram
            </button>
          )}

          {botUnavailable && (
            <p className="text-xs text-muted-foreground">
              绑定功能即将开放(等待 bot 配置)· 稍后再来。
            </p>
          )}

          {bindInfo && (
            <BindInstructions info={bindInfo} onRefresh={handleRefresh} />
          )}
        </>
      )}
    </div>
  )
}

function BindInstructions({
  info,
  onRefresh,
}: {
  info: BindTokenResult
  onRefresh: () => void
}) {
  const minutes = Math.max(1, Math.round(info.expires_in / 60))
  return (
    <div className="space-y-3">
      {info.deep_link ? (
        <div className="flex flex-col items-center gap-2">
          <div className="rounded-md bg-white p-2">
            <QRCodeSVG value={info.deep_link} size={148} />
          </div>
          <p className="text-xs text-muted-foreground">用手机 Telegram 扫码,或</p>
          <a
            href={info.deep_link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep"
          >
            在 Telegram 中打开
          </a>
        </div>
      ) : (
        <div className="rounded-md border border-paper bg-background p-3 text-xs">
          <p className="mb-1 text-muted-foreground">在官方 bot 里发送:</p>
          <code className="break-all font-mono text-foreground">
            /start {info.token}
          </code>
        </div>
      )}
      <p className="text-center text-[11px] text-muted-foreground/80">
        链接 {minutes} 分钟内有效 · 在 bot 里完成 /start 后点下方刷新
      </p>
      <button
        type="button"
        onClick={onRefresh}
        className="w-full rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground transition-colors hover:bg-cream"
      >
        我已完成绑定 · 刷新状态
      </button>
    </div>
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
