'use client'

/**
 * 设置页 · 消息推送配置 section · 0025 G2a 统一 Telegram bot。
 *
 * 0025 改动:移除飞书 + per-user TG token 手填;Telegram 经统一 bot 的 /start 绑定。
 * 本期(G2a)只展示绑定状态 + 测试按钮 + 事件总开关;完整绑定 UX(扫码 / deep link)
 * 在 G5 接入。Toast 配色:成功帝王金,失败中国红,绝不绿色。
 */

import { useQueryClient } from '@tanstack/react-query'
import { Check, Copy, Loader2 } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  NOTIFICATIONS_KEY,
  useNotificationConfig,
  useSaveNotificationConfig,
  useSendTestNotification,
} from '@/hooks/use-notifications'
import { useCreateFeishuBindToken, useUnbindFeishu } from '@/hooks/use-feishu'
import { useCreateBindToken, useUnbindTelegram } from '@/hooks/use-telegram'
import {
  type FeishuBindTokenResult,
  FeishuApiError,
  feishuBotOpenLink,
} from '@/lib/api/feishu'
import type { NotificationConfig } from '@/lib/api/notifications'
import { type BindTokenResult, TelegramApiError } from '@/lib/api/telegram'
import { cn } from '@/lib/utils'

// 0028 N2 · 时区预设(覆盖主要交易市场 · 后端 zoneinfo 校验通过的 IANA 名)
const TZ_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'Asia/Shanghai', label: '北京 / 上海 (UTC+8)' },
  { value: 'Asia/Tokyo', label: '东京 (UTC+9)' },
  { value: 'Asia/Singapore', label: '新加坡 (UTC+8)' },
  { value: 'Europe/London', label: '伦敦 (UTC+0/+1)' },
  { value: 'America/New_York', label: '纽约 (UTC-5/-4)' },
  { value: 'UTC', label: 'UTC' },
]

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
  const feishuBound = config?.has_feishu ?? false

  return (
    <section className="mb-10">
      <h2 className="mb-2 font-serif text-xl font-bold text-foreground">
        消息推送
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">
        绑定 Telegram / 飞书后,成交通知 / 价格异动会推送到对应渠道 · 未绑定只有站内提示
      </p>

      <div className="space-y-4">
        {/* Telegram 绑定(G3 · deep link + 二维码 + 解绑 + 重绑提示)*/}
        <TelegramCard bound={bound} />

        {/* 飞书绑定(ADR 0032 阶段三 · 绑定码 + 解绑)*/}
        <FeishuCard bound={feishuBound} />

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

        {/* 0028 N2 · 安静时段配置(在该窗口内吞普通告警 · 紧急豁免照发)*/}
        <QuietHoursCard config={config ?? null} />
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
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 break-all font-mono text-foreground">
              /start {info.token}
            </code>
            <CopyButton
              value={`/start ${info.token}`}
              copiedLabel="已复制绑定指令"
            />
          </div>
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

// ===== 飞书绑定卡(ADR 0032 阶段三 · 对称 Telegram)=====

function FeishuCard({ bound }: { bound: boolean }) {
  const createToken = useCreateFeishuBindToken()
  const unbind = useUnbindFeishu()
  const queryClient = useQueryClient()
  const [bindInfo, setBindInfo] = useState<FeishuBindTokenResult | null>(null)
  const [appUnavailable, setAppUnavailable] = useState(false)

  async function handleBind() {
    setAppUnavailable(false)
    try {
      setBindInfo(await createToken.mutateAsync())
    } catch (e) {
      if (e instanceof FeishuApiError && e.status === 503) {
        setAppUnavailable(true)
      } else {
        toast.error(e instanceof Error ? e.message : '生成绑定码失败')
      }
    }
  }

  async function handleUnbind() {
    try {
      await unbind.mutateAsync()
      setBindInfo(null)
      toast.success('已解绑飞书')
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
        <span className="text-xl" aria-hidden="true">🪶</span>
        <h3 className="font-serif text-base font-bold text-foreground">飞书</h3>
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
            已绑定到你的飞书 · 成交 / 价格异动 / 告警会推送到这里。
          </p>
          <div className="flex flex-wrap gap-2">
            <TestButton disabled={false} channel="feishu" channelLabel="飞书" />
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
          {!bindInfo && !appUnavailable && (
            <button
              type="button"
              onClick={handleBind}
              disabled={createToken.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:cursor-not-allowed disabled:opacity-50"
            >
              {createToken.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              绑定飞书
            </button>
          )}

          {appUnavailable && (
            <p className="text-xs text-muted-foreground">
              飞书绑定即将开放(等待应用配置)· 稍后再来。
            </p>
          )}

          {bindInfo && (
            <FeishuBindInstructions info={bindInfo} onRefresh={handleRefresh} />
          )}
        </>
      )}
    </div>
  )
}

function FeishuBindInstructions({
  info,
  onRefresh,
}: {
  info: FeishuBindTokenResult
  onRefresh: () => void
}) {
  const minutes = Math.max(1, Math.round(info.expires_in / 60))
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-paper bg-background p-3 text-xs">
        <p className="mb-1 text-muted-foreground">在飞书里打开点金 Midas 应用,发送下面这串绑定码:</p>
        <div className="flex items-center gap-2">
          <code className="min-w-0 flex-1 break-all font-mono text-foreground">
            {info.token}
          </code>
          <CopyButton value={info.token} copiedLabel="已复制绑定码" />
        </div>
        <p className="mt-1 text-muted-foreground/80">
          (也可发「/bind {info.token}」· 直接粘贴绑定码同样可绑)
        </p>
      </div>
      {info.app_id && (
        <a
          href={feishuBotOpenLink(info.app_id)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep"
        >
          🪶 在飞书中打开 → 粘贴绑定码
        </a>
      )}
      <p className="text-center text-[11px] text-muted-foreground/80">
        先复制绑定码 · 点上方按钮直达会话 · 粘贴发送 · 完成后点下方刷新
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

// ===== 0028 N2 · 安静时段卡 =====

function QuietHoursCard({ config }: { config: NotificationConfig | null }) {
  const saveMutation = useSaveNotificationConfig()

  // 本地表单态(载入后 sync,提交时 diff 出真实改动 — 但简单起见全字段一起 PUT)
  const [enabled, setEnabled] = useState(true)
  const [startHour, setStartHour] = useState(23)
  const [endHour, setEndHour] = useState(7)
  const [tz, setTz] = useState('Asia/Shanghai')

  useEffect(() => {
    if (config) {
      setEnabled(config.quiet_hours_enabled)
      setStartHour(config.quiet_hours_start)
      setEndHour(config.quiet_hours_end)
      setTz(config.quiet_hours_tz)
    }
  }, [config])

  const crossNight = startHour > endHour
  const tzLabel =
    TZ_OPTIONS.find((opt) => opt.value === tz)?.label ?? tz

  async function handleSave() {
    try {
      await saveMutation.mutateAsync({
        quiet_hours_enabled: enabled,
        quiet_hours_start: startHour,
        quiet_hours_end: endHour,
        quiet_hours_tz: tz,
      })
      toast.success('安静时段已保存')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    }
  }

  return (
    <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-xl" aria-hidden="true">🌙</span>
        <h3 className="font-serif text-base font-bold text-foreground">
          告警安静时段
        </h3>
        <span
          className={cn(
            'rounded border px-1.5 py-0.5 font-mono text-[10px]',
            enabled
              ? 'border-gold bg-gold/[0.08] text-gold'
              : 'border-paper text-muted-foreground/70',
          )}
        >
          {enabled ? '已启用' : '已关闭'}
        </span>
      </div>

      <p className="mb-3 text-xs text-muted-foreground">
        在此时段内,自选异动 / 规则告警等普通推送会被静默。
        <span className="font-medium text-foreground"> 成交 / 强平等关键事件不受影响</span>
        ,夜间也会照常推送。
      </p>

      {/* 总开关 */}
      <div className="mb-3">
        <Toggle
          label="启用安静时段"
          hint={
            enabled
              ? `当前 ${formatHour(startHour)} – ${
                  crossNight ? '次日 ' : ''
                }${formatHour(endHour)} · ${tzLabel}`
              : '关闭后所有时段都会推送(夜间不静默)'
          }
          checked={enabled}
          onChange={setEnabled}
        />
      </div>

      {/* 起止 + 时区:仅在启用时显示编辑控件,关闭时只读保留值 */}
      <fieldset
        disabled={!enabled}
        className={cn(
          'space-y-3 transition-opacity',
          !enabled && 'pointer-events-none opacity-50',
        )}
      >
        <div className="grid grid-cols-2 gap-3">
          <HourSelect
            label="起始时间"
            value={startHour}
            onChange={setStartHour}
          />
          <HourSelect
            label={crossNight ? '结束时间(次日)' : '结束时间'}
            value={endHour}
            onChange={setEndHour}
          />
        </div>

        <div>
          <label
            htmlFor="quiet-hours-tz"
            className="mb-1 block text-xs text-muted-foreground"
          >
            时区
          </label>
          <select
            id="quiet-hours-tz"
            value={tz}
            onChange={(e) => setTz(e.target.value)}
            className="w-full rounded-md border border-paper bg-background px-3 py-2 text-sm text-foreground focus:border-midas-red focus:outline-none focus:ring-1 focus:ring-midas-red/30"
          >
            {TZ_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {crossNight && (
          <p className="rounded-md border border-paper bg-background px-3 py-2 text-[11px] text-muted-foreground">
            ⓘ 起始时间晚于结束时间 → 跨夜窗口(如 23:00 静默到次日 07:00)
          </p>
        )}
      </fieldset>

      <div className="mt-4">
        <SaveButton onClick={handleSave} pending={saveMutation.isPending}>
          保存安静时段
        </SaveButton>
      </div>
    </div>
  )
}

function HourSelect({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (next: number) => void
}) {
  return (
    <div>
      <label
        htmlFor={`hour-${label}`}
        className="mb-1 block text-xs text-muted-foreground"
      >
        {label}
      </label>
      <select
        id={`hour-${label}`}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-md border border-paper bg-background px-3 py-2 text-sm text-foreground focus:border-midas-red focus:outline-none focus:ring-1 focus:ring-midas-red/30"
      >
        {Array.from({ length: 24 }, (_, h) => (
          <option key={h} value={h}>
            {formatHour(h)}
          </option>
        ))}
      </select>
    </div>
  )
}

function formatHour(h: number): string {
  return `${String(h).padStart(2, '0')}:00`
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

/**
 * 绑定码一键复制按钮 · 纯前端(navigator.clipboard)· 无后端 / 业务逻辑。
 * 成功反馈用帝王金 ✓(视觉系统:成功帝王金);clipboard 不可用时降级 error toast。
 */
function CopyButton({
  value,
  copiedLabel = '已复制',
}: {
  value: string
  copiedLabel?: string
}) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      toast.success(copiedLabel)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('复制失败 · 请手动选择复制')
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? '已复制' : '复制'}
      className="inline-flex shrink-0 items-center gap-1 rounded-md border border-paper bg-background px-2.5 py-1 text-xs text-foreground transition-colors hover:bg-cream"
    >
      {copied ? (
        <>
          <Check className="h-3 w-3 text-gold" aria-hidden="true" />
          已复制
        </>
      ) : (
        <>
          <Copy className="h-3 w-3" aria-hidden="true" />
          复制
        </>
      )}
    </button>
  )
}

function TestButton({
  disabled,
  channel = 'telegram',
  channelLabel = 'Telegram',
}: {
  disabled: boolean
  channel?: 'telegram' | 'feishu'
  channelLabel?: string
}) {
  const testMutation = useSendTestNotification()

  async function handleClick() {
    try {
      const result = await testMutation.mutateAsync(channel)
      if (result.ok) {
        toast.success(`${channelLabel} 测试消息已发送`)
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
      title={disabled ? `绑定 ${channelLabel} 后可用` : undefined}
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
