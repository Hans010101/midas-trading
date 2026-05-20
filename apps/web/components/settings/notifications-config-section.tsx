'use client'

/**
 * 设置页 · 消息推送配置 section · 0009 v2 UI 填充(Checkpoint U)。
 *
 * 飞书 webhook + TG bot token + chat_id · 各通道独立 「保存」+「发送测试」按钮。
 * 总开关:成交通知 / 价格异动 各一个 toggle。
 *
 * Toast 配色严守红线:成功用帝王金,失败用中国红,绝不绿色。
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

  // 本地输入 state · config 加载完同步初始值
  const [feishuUrl, setFeishuUrl] = useState('')
  const [tgToken, setTgToken] = useState('')
  const [tgChatId, setTgChatId] = useState('')
  const [tradeEnabled, setTradeEnabled] = useState(true)
  const [priceEnabled, setPriceEnabled] = useState(true)

  // 标记 token 字段是否被用户修改过(避免清空截断的 token)
  const [tokenTouched, setTokenTouched] = useState(false)

  useEffect(() => {
    if (config) {
      setFeishuUrl(config.feishu_webhook_url ?? '')
      // 截断 token 仅展示 · 不写入 input(避免提交时把截断版本当真 token 存)
      setTgToken('')
      setTokenTouched(false)
      setTgChatId(config.tg_chat_id ?? '')
      setTradeEnabled(config.trade_alert_enabled)
      setPriceEnabled(config.price_alert_enabled)
    }
  }, [config])

  async function saveFeishu() {
    try {
      await saveMutation.mutateAsync({
        feishu_webhook_url: feishuUrl,
      })
      toast.success('飞书配置已保存')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    }
  }

  async function saveTelegram() {
    try {
      const payload: Parameters<typeof saveMutation.mutateAsync>[0] = {
        tg_chat_id: tgChatId,
      }
      // token 仅在用户主动输入新值时写入 · 否则保留 DB 已有(避免被截断版本污染)
      if (tokenTouched) {
        payload.tg_bot_token = tgToken
      }
      await saveMutation.mutateAsync(payload)
      toast.success('Telegram 配置已保存')
      setTokenTouched(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    }
  }

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

  return (
    <section className="mb-10">
      <h2 className="mb-2 font-serif text-xl font-bold text-foreground">
        消息推送
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">
        填飞书 webhook 推飞书 · 填 TG bot 推 TG · 都填都推 · 都不填只有站内
      </p>

      <div className="space-y-4">
        {/* 飞书 */}
        <ChannelCard
          icon="📣"
          title="飞书机器人"
          subtitle="自定义关键词「点金」· 消息天然含此字样"
          configured={config?.has_feishu ?? false}
        >
          <div className="mb-3">
            <label
              htmlFor="feishu-url"
              className="mb-1 block text-xs text-muted-foreground"
            >
              Webhook URL
            </label>
            <input
              id="feishu-url"
              type="text"
              value={feishuUrl}
              onChange={(e) => setFeishuUrl(e.target.value)}
              placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
              className="h-10 w-full rounded-md border border-paper bg-background px-3 font-mono text-xs text-foreground placeholder:text-muted-foreground/40"
            />
          </div>
          <ButtonRow>
            <SaveButton onClick={saveFeishu} pending={saveMutation.isPending}>
              保存飞书配置
            </SaveButton>
            <TestButton channel="feishu" />
          </ButtonRow>
        </ChannelCard>

        {/* Telegram */}
        <ChannelCard
          icon="✈️"
          title="Telegram bot"
          subtitle="到 @BotFather 申请 token,把 bot 加进群拿 chat_id"
          configured={config?.has_telegram ?? false}
        >
          <div className="mb-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label
                htmlFor="tg-token"
                className="mb-1 block text-xs text-muted-foreground"
              >
                Bot Token
                {config?.tg_bot_token && !tokenTouched && (
                  <span className="ml-2 font-mono text-[10px] text-muted-foreground/70">
                    已保存 · {config.tg_bot_token}
                  </span>
                )}
              </label>
              <input
                id="tg-token"
                type="password"
                value={tgToken}
                onChange={(e) => {
                  setTgToken(e.target.value)
                  setTokenTouched(true)
                }}
                placeholder={
                  config?.tg_bot_token
                    ? '已保存 · 输入新 token 替换'
                    : '123456789:ABC...XYZ'
                }
                className="h-10 w-full rounded-md border border-paper bg-background px-3 font-mono text-xs text-foreground placeholder:text-muted-foreground/40"
              />
            </div>
            <div>
              <label
                htmlFor="tg-chat-id"
                className="mb-1 block text-xs text-muted-foreground"
              >
                Chat ID
              </label>
              <input
                id="tg-chat-id"
                type="text"
                value={tgChatId}
                onChange={(e) => setTgChatId(e.target.value)}
                placeholder="-100123456789"
                className="h-10 w-full rounded-md border border-paper bg-background px-3 font-mono text-xs text-foreground placeholder:text-muted-foreground/40"
              />
            </div>
          </div>
          <ButtonRow>
            <SaveButton onClick={saveTelegram} pending={saveMutation.isPending}>
              保存 Telegram 配置
            </SaveButton>
            <TestButton channel="telegram" />
          </ButtonRow>
        </ChannelCard>

        {/* 总开关 */}
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

      <p className="mt-4 text-[10px] text-muted-foreground/70">
        ⚠ Token / Webhook URL 在数据库以明文存储(M0)· M1 升级加密
      </p>
    </section>
  )
}

// ===== sub-components =====

interface ChannelCardProps {
  icon: string
  title: string
  subtitle: string
  configured: boolean
  children: React.ReactNode
}

function ChannelCard({
  icon, title, subtitle, configured, children,
}: ChannelCardProps) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
      <div className="mb-3 flex items-baseline justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden="true">{icon}</span>
          <h3 className="font-serif text-base font-bold text-foreground">
            {title}
          </h3>
          {configured && (
            <span className="rounded border border-gold bg-gold/[0.08] px-1.5 py-0.5 font-mono text-[10px] text-gold">
              ✓ 已配置
            </span>
          )}
        </div>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">{subtitle}</p>
      {children}
    </div>
  )
}

function ButtonRow({ children }: { children: React.ReactNode }) {
  return <div className="flex gap-2">{children}</div>
}

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

function TestButton({ channel }: { channel: 'feishu' | 'telegram' }) {
  const testMutation = useSendTestNotification()

  async function handleClick() {
    try {
      const result = await testMutation.mutateAsync(channel)
      if (result.ok) {
        toast.success(
          channel === 'feishu' ? '飞书测试消息已发送' : 'TG 测试消息已发送',
        )
      } else {
        toast.error(
          `${channel === 'feishu' ? '飞书' : 'TG'} 推送失败 · ${result.error ?? '未知原因'}`,
        )
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '请求失败')
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={testMutation.isPending}
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
