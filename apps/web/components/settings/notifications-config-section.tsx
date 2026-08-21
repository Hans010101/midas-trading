'use client'

/**
 * 设置页 · 消息推送配置 section · 0025 G2a 统一 Telegram bot。
 *
 * 0025 改动:移除飞书 + per-user TG token 手填;Telegram 经统一 bot 的 /start 绑定。
 * 本期(G2a)只展示绑定状态 + 测试按钮 + 事件总开关;完整绑定 UX(扫码 / deep link)
 * 在 G5 接入。Toast 配色:成功帝王金,失败中国红,绝不绿色。
 */

import { useQueryClient } from '@tanstack/react-query'
import { Check, Copy, Loader2, Lock } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import {
  NOTIFICATIONS_KEY,
  useNotificationConfig,
  useSaveNotificationConfig,
  useSendTestNotification,
} from '@/hooks/use-notifications'
import { useCreateFeishuBindToken, useUnbindFeishu } from '@/hooks/use-feishu'
import { useMe } from '@/hooks/use-me'
import { useQuota } from '@/hooks/use-quota'
import {
  hasFullFeatureAccess,
  MEMBERSHIP_GATING_ENABLED,
} from '@/lib/features'
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
const TZ_OPTIONS: Array<{ value: string; en: string; zh: string }> = [
  { value: 'Asia/Shanghai', en: 'Beijing / Shanghai (UTC+8)', zh: '北京 / 上海 (UTC+8)' },
  { value: 'Asia/Tokyo', en: 'Tokyo (UTC+9)', zh: '东京 (UTC+9)' },
  { value: 'Asia/Singapore', en: 'Singapore (UTC+8)', zh: '新加坡 (UTC+8)' },
  { value: 'Europe/London', en: 'London (UTC+0/+1)', zh: '伦敦 (UTC+0/+1)' },
  { value: 'America/New_York', en: 'New York (UTC-5/-4)', zh: '纽约 (UTC-5/-4)' },
  { value: 'UTC', en: 'UTC', zh: 'UTC' },
]

export function NotificationsConfigSection() {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const { data: config, isLoading } = useNotificationConfig()
  const { data: me } = useMe()
  const saveMutation = useSaveNotificationConfig()

  const [tradeEnabled, setTradeEnabled] = useState(true)
  const [priceEnabled, setPriceEnabled] = useState(true)
  const [weeklyReportEnabled, setWeeklyReportEnabled] = useState(false)
  const [econAlertEnabled, setEconAlertEnabled] = useState(true)
  const [econAlertMinutes, setEconAlertMinutes] = useState<15 | 30 | 60>(30)

  useEffect(() => {
    if (config) {
      setTradeEnabled(config.trade_alert_enabled)
      setPriceEnabled(config.price_alert_enabled)
      setWeeklyReportEnabled(config.weekly_report_enabled)
      setEconAlertEnabled(config.econ_alert_enabled)
      setEconAlertMinutes(config.econ_alert_minutes)
    }
  }, [config])

  async function saveSwitches() {
    try {
      await saveMutation.mutateAsync({
        trade_alert_enabled: tradeEnabled,
        price_alert_enabled: priceEnabled,
        weekly_report_enabled: weeklyReportEnabled,
        econ_alert_enabled: econAlertEnabled,
        econ_alert_minutes: econAlertMinutes,
      })
      toast.success(en ? 'Notification settings saved' : '推送开关已保存')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : en ? 'Unable to save settings' : '保存失败')
    }
  }

  if (isLoading) {
    return <p className="py-4 text-sm text-muted-foreground">{en ? 'Loading…' : '载入中…'}</p>
  }

  const bound = config?.has_telegram ?? false
  const feishuBound = config?.has_feishu ?? false
  // 飞书仅对管理员展示(内部小范围继续用)· 普通用户隐藏绑定入口(★代码/端点/字段不删,仅 UI 按角色渲染)·
  // 已绑定的普通用户不主动解绑、推送照常,只是看不到「绑定入口」。
  const isAdmin = me?.role === 'admin'

  return (
    <section className="mb-10">
      <h2 className="mb-2 font-serif text-xl font-bold text-foreground">
        {en ? 'Message notifications' : '消息推送'}
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">
        {en
          ? `Bind Telegram${isAdmin ? ' or Feishu' : ''} to receive trade, price and rule alerts outside Midas. Unbound channels continue to receive in-app notifications only.`
          : `绑定 Telegram${isAdmin ? ' / 飞书' : ''}后,成交通知 / 价格异动会推送到对应渠道 · 未绑定只有站内提示`}
      </p>

      <div className="space-y-4">
        {/* Telegram 绑定(G3 · deep link + 二维码 + 解绑 + 重绑提示)*/}
        <TelegramCard bound={bound} />

        {/* 飞书绑定(ADR 0032 阶段三)· ★仅管理员可见(内部小范围用)· 代码/端点/字段全保留不删 */}
        {isAdmin && <FeishuCard bound={feishuBound} />}

        {/* 邮件推送/订阅(图标与上方 TG ✈️ / 飞书 🪶 同 emoji 风格)*/}
        <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
          <h3 className="mb-3 flex items-center gap-2 font-serif text-base font-bold text-foreground">
            <span className="text-xl" aria-hidden="true">📧</span>
            {en ? 'Email notifications' : '邮件推送/订阅'}
          </h3>
          <div className="mb-3 space-y-2">
            <Toggle
              locale={locale}
              label={en ? 'Trade notification' : '成交通知'}
              hint={en ? 'Sent after an order fills' : '下单成交后推送'}
              checked={tradeEnabled}
              onChange={setTradeEnabled}
            />
            <Toggle
              locale={locale}
              label={en ? 'Price alert' : '价格异动通知'}
              hint={en ? 'Watchlist ±5% · Five-minute deduplication per symbol' : '自选股 ±5% · 5 分钟同标的去重'}
              checked={priceEnabled}
              onChange={setPriceEnabled}
            />
            <Toggle
              locale={locale}
              label={en ? 'Economic calendar reminder' : '财经事件提醒'}
              hint={en ? 'High- and medium-impact events · In-app and bound channels' : '中高重要度事件 · 站内及已绑定外部通道'}
              checked={econAlertEnabled}
              onChange={setEconAlertEnabled}
            />
            {econAlertEnabled && (
              <label className="flex items-center justify-between gap-4 rounded-md border border-paper px-3 py-2 text-sm">
                <span>{en ? 'Notify me before the event' : '提前提醒时间'}</span>
                <select
                  value={econAlertMinutes}
                  onChange={(event) => setEconAlertMinutes(Number(event.target.value) as 15 | 30 | 60)}
                  className="rounded border border-paper bg-background px-2 py-1"
                >
                  <option value={15}>{en ? '15 minutes' : '15 分钟'}</option>
                  <option value={30}>{en ? '30 minutes' : '30 分钟'}</option>
                  <option value={60}>{en ? '60 minutes' : '60 分钟'}</option>
                </select>
              </label>
            )}
            <Toggle
              locale={locale}
              label={en ? 'Market weekly report' : '订阅市场周报'}
              hint={
                en
                  ? 'Full-market report emailed every Monday, including a PDF'
                  : '每周一全市场周报发到邮箱(含 PDF)· TG/飞书提示已发邮箱'
              }
              checked={weeklyReportEnabled}
              onChange={setWeeklyReportEnabled}
            />
          </div>
          <SaveButton onClick={saveSwitches} pending={saveMutation.isPending}>
            {en ? 'Save' : '保存开关'}
          </SaveButton>
        </div>

        {/* 做T M2-2 · 做T信号 TG 通知(★Pro 专属订阅开关 · 默认关 opt-in · 本刀只订阅不真发)*/}
        <DottAlertCard config={config ?? null} bound={bound} />

        {/* 0028 N2 · 安静时段配置(在该窗口内吞普通告警 · 紧急豁免照发)*/}
        <QuietHoursCard config={config ?? null} />
      </div>
    </section>
  )
}

// ===== 做T信号 TG 通知卡(做T M2-2 · ★Pro 专属订阅开关 · 默认关 opt-in · 本刀只订阅不真发)=====

function DottAlertCard({
  config,
  bound,
}: {
  config: NotificationConfig | null
  bound: boolean
}) {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const { data: quota } = useQuota()
  const hasAccess = hasFullFeatureAccess(quota !== undefined, quota?.plan)
  const router = useRouter()
  const saveMutation = useSaveNotificationConfig()
  // M2-4 拆两体系:定时全景(digest)/ 行情转换(transition)· 各自独立开关
  const [digest, setDigest] = useState(false)
  const [transition, setTransition] = useState(false)

  useEffect(() => {
    if (config) {
      setDigest(config.dott_digest_enabled)
      setTransition(config.dott_transition_enabled)
    }
  }, [config])

  // 通用:乐观切换 + 只发该字段(局部更新 · 存 DB notification_config 非 cookie)+ 失败回滚
  async function toggleField(
    field: 'dott_digest_enabled' | 'dott_transition_enabled',
    next: boolean,
    setLocal: (v: boolean) => void,
    label: string,
  ) {
    setLocal(next)
    try {
      await saveMutation.mutateAsync({ [field]: next })
      toast.success(
        en
          ? `${label} ${next ? 'enabled' : 'disabled'}`
          : next ? `已开启${label}` : `已关闭${label}`,
      )
    } catch (e) {
      setLocal(!next) // ★后端非 Pro 设 true → 403,回滚 + 提示(Pro 双层 gate 第二道)
      toast.error(e instanceof Error ? e.message : en ? 'Unable to save setting' : '保存失败')
    }
  }

  return (
    <DottAlertView
      isPro={hasAccess}
      bound={bound}
      digestEnabled={digest}
      transitionEnabled={transition}
      pending={saveMutation.isPending}
      locale={locale}
      onToggleDigest={(next) =>
        toggleField(
          'dott_digest_enabled',
          next,
          setDigest,
          en ? 'Hourly digest' : '做T定时全景',
        )
      }
      onToggleTransition={(next) =>
        toggleField(
          'dott_transition_enabled',
          next,
          setTransition,
          en ? 'Transition alert' : '做T行情转换',
        )
      }
      onUpgrade={() => router.push('/account/membership')}
    />
  )
}

/**
 * 做T信号卡【纯展示】(props 驱动 · 无 hooks)· 登录墙页用 renderToString 钉死 Pro/非 Pro 两态。
 * M2-4:「做T信号」分组(Pro 专属),组内两个开关 —— 做T定时全景(体系1)/ 做T行情转换(体系2)。
 * 非 Pro:两开关禁用 + 「Pro 专属」徽章 + 「开通 Pro」引导;Pro:两开关可操作(未绑 TG 提示先绑定)。
 */
export function DottAlertView({
  isPro,
  bound,
  digestEnabled,
  transitionEnabled,
  pending,
  onToggleDigest,
  onToggleTransition,
  onUpgrade,
  locale = 'zh',
}: {
  isPro: boolean
  bound: boolean
  digestEnabled: boolean
  transitionEnabled: boolean
  pending: boolean
  onToggleDigest: (next: boolean) => void
  onToggleTransition: (next: boolean) => void
  onUpgrade: () => void
  locale?: 'en' | 'zh'
}) {
  const en = locale === 'en'
  const gated = MEMBERSHIP_GATING_ENABLED && !isPro
  return (
    <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
      <h3 className="mb-1 flex items-center gap-2 font-serif text-base font-bold text-foreground">
        <span className="text-xl" aria-hidden="true">📈</span>
        {en ? 'Day-trade signal notifications' : '做T信号推送'}
      </h3>
      <p className="mb-3 text-xs text-muted-foreground">
        {en
          ? 'Bollinger day-trade signals for crypto perpetuals are sent to your bound Telegram channel'
          : '布林做T 信号(加密永续)推送到你绑定的 Telegram'}
        {isPro && !bound
          ? en
            ? ' · Bind Telegram above to receive them'
            : ' · ⚠ 需先绑定 Telegram(上方)才会真正收到'
          : ''}
      </p>

      {!gated ? (
        <div className="space-y-2">
          <Toggle
            locale={locale}
            label={en ? 'Day-trade hourly digest' : '做T定时全景'}
            hint={
              en
                ? 'Hourly top-five bullish, neutral and bearish overview'
                : '每小时推送多空分类概览(偏多/中性/偏空各前 5)'
            }
            checked={digestEnabled}
            onChange={onToggleDigest}
          />
          <Toggle
            locale={locale}
            label={en ? 'Day-trade transition alert' : '做T行情转换'}
            hint={
              en
                ? 'Sent when the Bollinger structure changes state'
                : '布林结构发生转换时推送(状态转换提醒)'
            }
            checked={transitionEnabled}
            onChange={onToggleTransition}
          />
          {pending && (
            <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground/70">
              <Loader2 className="h-3 w-3 animate-spin" /> {en ? 'Saving…' : '保存中…'}
            </p>
          )}
        </div>
      ) : (
        // 非 Pro:两开关禁用 + Pro 标签 + 点击引导开通(★前端第一道门 · 后端 PUT 是第二道)
        <button
          type="button"
          onClick={onUpgrade}
          className="flex w-full items-center justify-between gap-3 rounded-md border border-dashed border-gold/50 bg-background px-3 py-2 text-left transition-colors hover:bg-gold/[0.04]"
        >
          <div className="flex items-center gap-2">
            <Lock className="h-4 w-4 shrink-0 text-gold" aria-hidden="true" />
            <div>
              <div className="text-sm text-foreground">
                {en ? 'Day-trade digest / transition alerts' : '做T定时全景 / 做T行情转换'}
              </div>
              <div className="text-xs text-muted-foreground/70">
                {en ? 'Available with Pro' : 'Pro 会员专属 · 点此开通后可订阅'}
              </div>
            </div>
          </div>
          <span className="shrink-0 font-medium text-midas-red">
            {en ? 'Upgrade' : '开通 Pro'}
          </span>
        </button>
      )}
    </div>
  )
}

// ===== Telegram 绑定卡 =====

function TelegramCard({ bound }: { bound: boolean }) {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
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
        toast.error(e instanceof Error ? e.message : en ? 'Unable to create binding link' : '生成绑定链接失败')
      }
    }
  }

  async function handleUnbind() {
    try {
      await unbind.mutateAsync()
      setBindInfo(null)
      toast.success(en ? 'Telegram unbound' : '已解绑 Telegram')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : en ? 'Unable to unbind Telegram' : '解绑失败')
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
          {bound ? (en ? '✓ Bound' : '✓ 已绑定') : (en ? 'Not bound' : '未绑定')}
        </span>
      </div>

      {bound ? (
        <>
          <p className="mb-3 text-xs text-muted-foreground">
            {en
              ? 'Trade notifications, price alerts and rules are sent to your Telegram.'
              : '已绑定到你的 Telegram · 成交 / 价格异动 / 告警会推送到这里。'}
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
              {en ? 'Unbind' : '解绑'}
            </button>
          </div>
        </>
      ) : (
        <>
          {/* D3 重绑提示 · 帝王金强调(G2a 已清空旧 chat_id,存量绑定失效)*/}
          <div className="mb-3 rounded-md border border-gold/40 bg-gold/[0.06] px-3 py-2 text-xs text-foreground">
            <span className="font-medium text-gold">
              {en ? 'Bind or re-bind Telegram' : '请绑定 / 重新绑定 Telegram'}
            </span>
            <br />
            {en
              ? 'Notifications now use the official Midas bot. Existing legacy bindings must be renewed; new users can bind directly.'
              : '推送已升级为统一官方 bot。若你此前绑定过,旧绑定已失效,请重新绑定;首次使用直接绑定即可。'}
          </div>

          {!bindInfo && !botUnavailable && (
            <button
              type="button"
              onClick={handleBind}
              disabled={createToken.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:cursor-not-allowed disabled:opacity-50"
            >
              {createToken.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {en ? 'Bind Telegram' : '绑定 Telegram'}
            </button>
          )}

          {botUnavailable && (
            <p className="text-xs text-muted-foreground">
              {en
                ? 'Telegram binding is awaiting bot configuration. Please check back later.'
                : '绑定功能即将开放(等待 bot 配置)· 稍后再来。'}
            </p>
          )}

          {bindInfo && (
            <BindInstructions info={bindInfo} onRefresh={handleRefresh} locale={locale} />
          )}
        </>
      )}
    </div>
  )
}

function BindInstructions({
  info,
  onRefresh,
  locale,
}: {
  info: BindTokenResult
  onRefresh: () => void
  locale: 'en' | 'zh'
}) {
  const en = locale === 'en'
  const minutes = Math.max(1, Math.round(info.expires_in / 60))
  return (
    <div className="space-y-3">
      {info.deep_link ? (
        <div className="flex flex-col items-center gap-2">
          <div className="rounded-md bg-white p-2">
            <QRCodeSVG value={info.deep_link} size={148} />
          </div>
          <p className="text-xs text-muted-foreground">
            {en ? 'Scan with Telegram on your phone, or' : '用手机 Telegram 扫码,或'}
          </p>
          <a
            href={info.deep_link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep"
          >
            {en ? 'Open in Telegram' : '在 Telegram 中打开'}
          </a>
        </div>
      ) : (
        <div className="rounded-md border border-paper bg-background p-3 text-xs">
          <p className="mb-1 text-muted-foreground">
            {en ? 'Send this command to the official bot:' : '在官方 bot 里发送:'}
          </p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 break-all font-mono text-foreground">
              /start {info.token}
            </code>
            <CopyButton
              value={`/start ${info.token}`}
              copiedLabel={en ? 'Binding command copied' : '已复制绑定指令'}
            />
          </div>
        </div>
      )}
      <p className="text-center text-[11px] text-muted-foreground/80">
        {en
          ? `Link valid for ${minutes} minutes · Complete /start in the bot, then refresh the status`
          : `链接 ${minutes} 分钟内有效 · 在 bot 里完成 /start 后点下方刷新`}
      </p>
      <button
        type="button"
        onClick={onRefresh}
        className="w-full rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground transition-colors hover:bg-cream"
      >
        {en ? 'Binding complete · Refresh status' : '我已完成绑定 · 刷新状态'}
      </button>
    </div>
  )
}

// ===== 飞书绑定卡(ADR 0032 阶段三 · 对称 Telegram)=====

function FeishuCard({ bound }: { bound: boolean }) {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const createToken = useCreateFeishuBindToken()
  const unbind = useUnbindFeishu()
  const queryClient = useQueryClient()
  const [bindInfo, setBindInfo] = useState<FeishuBindTokenResult | null>(null)
  const [appUnavailable, setAppUnavailable] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  async function handleBind() {
    setAppUnavailable(false)
    try {
      setBindInfo(await createToken.mutateAsync())
    } catch (e) {
      if (e instanceof FeishuApiError && e.status === 503) {
        setAppUnavailable(true)
      } else {
        toast.error(e instanceof Error ? e.message : en ? 'Unable to create binding code' : '生成绑定码失败')
      }
    }
  }

  async function handleUnbind() {
    try {
      await unbind.mutateAsync()
      setBindInfo(null)
      toast.success(en ? 'Feishu unbound' : '已解绑飞书')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : en ? 'Unable to unbind Feishu' : '解绑失败')
    }
  }

  async function handleRefresh() {
    setRefreshing(true)
    try {
      await queryClient.refetchQueries({
        queryKey: NOTIFICATIONS_KEY.config,
        type: 'active',
      }, { throwOnError: true })
      const latest = queryClient.getQueryData<NotificationConfig>(NOTIFICATIONS_KEY.config)
      if (latest?.has_feishu) {
        setBindInfo(null)
        toast.success(en ? 'Feishu binding confirmed' : '飞书绑定已确认')
      } else {
        toast.error(en
          ? 'No binding event received. Send the binding code to the bot, then try again.'
          : '尚未收到绑定事件，请把绑定码作为一条消息发送给机器人后再刷新')
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : en ? 'Unable to refresh status' : '刷新状态失败')
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-xl" aria-hidden="true">🪶</span>
        <h3 className="font-serif text-base font-bold text-foreground">
          {en ? 'Feishu' : '飞书'}
        </h3>
        <span
          className={cn(
            'rounded border px-1.5 py-0.5 font-mono text-[10px]',
            bound
              ? 'border-gold bg-gold/[0.08] text-gold'
              : 'border-paper text-muted-foreground/70',
          )}
        >
          {bound ? (en ? '✓ Bound' : '✓ 已绑定') : (en ? 'Not bound' : '未绑定')}
        </span>
      </div>

      {bound ? (
        <>
          <p className="mb-3 text-xs text-muted-foreground">
            {en
              ? 'Trade notifications, price alerts and rules are sent to your Feishu.'
              : '已绑定到你的飞书 · 成交 / 价格异动 / 告警会推送到这里。'}
          </p>
          <div className="flex flex-wrap gap-2">
            <TestButton
              disabled={false}
              channel="feishu"
              channelLabel={en ? 'Feishu' : '飞书'}
            />
            <button
              type="button"
              onClick={handleUnbind}
              disabled={unbind.isPending}
              className="inline-flex items-center gap-1.5 rounded-md border border-midas-red/40 bg-background px-4 py-2 text-sm text-midas-red transition-colors hover:bg-midas-red/[0.06] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {unbind.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {en ? 'Unbind' : '解绑'}
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
              {en ? 'Bind Feishu' : '绑定飞书'}
            </button>
          )}

          {appUnavailable && (
            <p className="text-xs text-muted-foreground">
              {en
                ? 'Feishu binding is awaiting app configuration. Please check back later.'
                : '飞书绑定即将开放(等待应用配置)· 稍后再来。'}
            </p>
          )}

          {bindInfo && (
            <FeishuBindInstructions
              info={bindInfo}
              onRefresh={handleRefresh}
              refreshing={refreshing}
              locale={locale}
            />
          )}
        </>
      )}
    </div>
  )
}

function FeishuBindInstructions({
  info,
  onRefresh,
  refreshing,
  locale,
}: {
  info: FeishuBindTokenResult
  onRefresh: () => Promise<void>
  refreshing: boolean
  locale: 'en' | 'zh'
}) {
  const en = locale === 'en'
  const minutes = Math.max(1, Math.round(info.expires_in / 60))
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-paper bg-background p-3 text-xs">
        <p className="mb-1 text-muted-foreground">
          {en
            ? 'Open the Midas app in Feishu and send this binding code:'
            : '在飞书里打开点金 Midas 应用,发送下面这串绑定码:'}
        </p>
        <div className="flex items-center gap-2">
          <code className="min-w-0 flex-1 break-all font-mono text-foreground">
            {info.token}
          </code>
          <CopyButton value={info.token} copiedLabel={en ? 'Binding code copied' : '已复制绑定码'} />
        </div>
        <p className="mt-1 text-muted-foreground/80">
          {en
            ? `(You can also send “/bind ${info.token}” or paste the code directly.)`
            : `(也可发「/bind ${info.token}」· 直接粘贴绑定码同样可绑)`}
        </p>
      </div>
      {info.app_id && (
        <a
          href={feishuBotOpenLink(info.app_id)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep"
        >
          {en ? '🪶 Open in Feishu → Paste binding code' : '🪶 在飞书中打开 → 粘贴绑定码'}
        </a>
      )}
      <p className="text-center text-[11px] text-muted-foreground/80">
        {en
          ? `Binding code valid for ${minutes} minutes · Copy it, open Feishu, send it, then refresh the status`
          : `绑定码 ${minutes} 分钟内有效 · 先复制 · 点「在飞书中打开」直达会话 · 粘贴发送 · 完成后点下方刷新`}
      </p>
      <button
        type="button"
        onClick={() => void onRefresh()}
        disabled={refreshing}
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground transition-colors hover:bg-cream disabled:cursor-wait disabled:opacity-60"
      >
        {refreshing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {en ? 'Binding complete · Refresh status' : '我已完成绑定 · 刷新状态'}
      </button>
    </div>
  )
}

// ===== 0028 N2 · 安静时段卡 =====

function QuietHoursCard({ config }: { config: NotificationConfig | null }) {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
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
    TZ_OPTIONS.find((opt) => opt.value === tz)?.[locale] ?? tz

  async function handleSave() {
    try {
      await saveMutation.mutateAsync({
        quiet_hours_enabled: enabled,
        quiet_hours_start: startHour,
        quiet_hours_end: endHour,
        quiet_hours_tz: tz,
      })
      toast.success(en ? 'Quiet hours saved' : '安静时段已保存')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : en ? 'Unable to save quiet hours' : '保存失败')
    }
  }

  return (
    <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-xl" aria-hidden="true">🌙</span>
        <h3 className="font-serif text-base font-bold text-foreground">
          {en ? 'Quiet hours' : '告警安静时段'}
        </h3>
        <span
          className={cn(
            'rounded border px-1.5 py-0.5 font-mono text-[10px]',
            enabled
              ? 'border-gold bg-gold/[0.08] text-gold'
              : 'border-paper text-muted-foreground/70',
          )}
        >
          {enabled ? (en ? 'Enabled' : '已启用') : (en ? 'Disabled' : '已关闭')}
        </span>
      </div>

      <p className="mb-3 text-xs text-muted-foreground">
        {en
          ? 'Routine watchlist and rule alerts are muted during this window.'
          : '在此时段内,自选异动 / 规则告警等普通推送会被静默。'}
        <span className="font-medium text-foreground">
          {en
            ? ' Critical events such as fills and liquidations are still delivered.'
            : ' 成交 / 强平等关键事件不受影响'}
        </span>
        {!en && ',夜间也会照常推送。'}
      </p>

      {/* 总开关 */}
      <div className="mb-3">
        <Toggle
          locale={locale}
          label={en ? 'Enable quiet hours' : '启用安静时段'}
          hint={
            enabled
              ? `${en ? 'Current' : '当前'} ${formatHour(startHour)} – ${
                  crossNight ? (en ? 'next day ' : '次日 ') : ''
                }${formatHour(endHour)} · ${tzLabel}`
              : en
                ? 'Notifications can be delivered at any time'
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
            label={en ? 'Start time' : '起始时间'}
            value={startHour}
            onChange={setStartHour}
          />
          <HourSelect
            label={
              en
                ? crossNight ? 'End time (next day)' : 'End time'
                : crossNight ? '结束时间(次日)' : '结束时间'
            }
            value={endHour}
            onChange={setEndHour}
          />
        </div>

        <div>
          <label
            htmlFor="quiet-hours-tz"
            className="mb-1 block text-xs text-muted-foreground"
          >
            {en ? 'Time zone' : '时区'}
          </label>
          <select
            id="quiet-hours-tz"
            value={tz}
            onChange={(e) => setTz(e.target.value)}
            className="w-full rounded-md border border-paper bg-background px-3 py-2 text-sm text-foreground focus:border-midas-red focus:outline-none focus:ring-1 focus:ring-midas-red/30"
          >
            {TZ_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt[locale]}
              </option>
            ))}
          </select>
        </div>

        {crossNight && (
          <p className="rounded-md border border-paper bg-background px-3 py-2 text-[11px] text-muted-foreground">
            {en
              ? 'ⓘ The end time falls on the next day, for example 23:00–07:00'
              : 'ⓘ 起始时间晚于结束时间 → 跨夜窗口(如 23:00 静默到次日 07:00)'}
          </p>
        )}
      </fieldset>

      <div className="mt-4">
        <SaveButton onClick={handleSave} pending={saveMutation.isPending}>
          {en ? 'Save quiet hours' : '保存安静时段'}
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
  copiedLabel,
}: {
  value: string
  copiedLabel?: string
}) {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      toast.success(copiedLabel ?? (en ? 'Copied' : '已复制'))
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error(en ? 'Copy failed · Select and copy the text manually' : '复制失败 · 请手动选择复制')
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? (en ? 'Copied' : '已复制') : (en ? 'Copy' : '复制')}
      className="inline-flex shrink-0 items-center gap-1 rounded-md border border-paper bg-background px-2.5 py-1 text-xs text-foreground transition-colors hover:bg-cream"
    >
      {copied ? (
        <>
          <Check className="h-3 w-3 text-gold" aria-hidden="true" />
          {en ? 'Copied' : '已复制'}
        </>
      ) : (
        <>
          <Copy className="h-3 w-3" aria-hidden="true" />
          {en ? 'Copy' : '复制'}
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
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const testMutation = useSendTestNotification()

  async function handleClick() {
    try {
      const result = await testMutation.mutateAsync(channel)
      if (result.ok) {
        toast.success(en ? `${channelLabel} test message sent` : `${channelLabel} 测试消息已发送`)
      } else {
        toast.error(
          en
            ? `Delivery failed · ${result.error ?? 'Unknown reason'}`
            : `推送失败 · ${result.error ?? '未知原因'}`,
        )
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : en ? 'Request failed' : '请求失败')
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || testMutation.isPending}
      title={disabled ? (en ? `Bind ${channelLabel} to enable testing` : `绑定 ${channelLabel} 后可用`) : undefined}
      className="inline-flex items-center gap-1.5 rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground transition-colors hover:bg-cream disabled:cursor-not-allowed disabled:opacity-50"
    >
      {testMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {en ? 'Send test' : '发送测试'}
    </button>
  )
}

interface ToggleProps {
  locale?: 'en' | 'zh'
  label: string
  hint: string
  checked: boolean
  onChange: (next: boolean) => void
}

function Toggle({ locale = 'zh', label, hint, checked, onChange }: ToggleProps) {
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
        {checked ? (locale === 'en' ? 'On' : '开') : (locale === 'en' ? 'Off' : '关')}
      </span>
    </label>
  )
}
