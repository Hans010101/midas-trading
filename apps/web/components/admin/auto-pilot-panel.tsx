'use client'

/**
 * X 营销自动托管 · 控制面板(自动托管 PR-4)。
 *
 * 状态卡(开关/熔断/日配额/时段)+ 开关按钮(★开启二次确认)+ 紧急熔断按钮(二次确认)。
 * 🔴 admin 端点(后端 AdminDep 403)· 状态每 15s 轮询保鲜(开启后日配额/熔断会变)。
 * ★开关默认 OFF · 开 = 全自动起草+发布上线;紧急熔断 = 立刻关停 + revoke 排队任务。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  getAutoPilotStatus,
  stopAutoPilot,
  toggleAutoPilot,
  toggleAutoPlatform,
  updateAutoDailyLimit,
  type BinanceSquareAccountKey,
} from '@/lib/api/x-auto'

// 平台标识 → 显示名(加平台 = registry 加一行后,这里补个显示名即可;缺省显示原标识)
const PLATFORM_LABEL: Record<string, string> = {
  binance_square: '币安广场',
  x: '𝕏(Twitter)',
}

const SOURCE_STATUS = {
  healthy: { label: '正常', className: 'border-green-200 bg-green-50 text-green-700' },
  error: { label: '异常', className: 'border-red-200 bg-red-50 text-red-700' },
  disabled: { label: '待配置', className: 'border-paper bg-muted text-muted-foreground' },
} as const

function StatChip({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className={`text-sm font-medium ${tone}`}>{value}</span>
    </div>
  )
}

function compact(value: number | null): string {
  return value === null ? '—' : new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

export function AutoPilotPanel({ token }: { token: string }) {
  const qc = useQueryClient()
  const [note, setNote] = useState('')

  const query = useQuery({
    queryKey: ['admin-x-auto-status'],
    queryFn: ({ signal }) => getAutoPilotStatus(token, signal),
    enabled: token !== '',
    refetchInterval: 15000, // 开启后日配额/熔断会动 · 15s 轮询保鲜
  })
  const invalidate = () => void qc.invalidateQueries({ queryKey: ['admin-x-auto-status'] })

  const toggleMut = useMutation({
    mutationFn: ({ enabled, accountKey }: {
      enabled: boolean
      accountKey: BinanceSquareAccountKey
    }) => toggleAutoPilot(token, enabled, accountKey),
    onSuccess: (s) => {
      setNote(s.enabled ? '✓ 自动托管已开启 · 系统将按守卫自动起草并发布' : '自动托管已关闭')
      invalidate()
    },
    onError: () => setNote('操作失败,请重试'),
  })

  const stopMut = useMutation({
    mutationFn: (accountKey?: BinanceSquareAccountKey) => stopAutoPilot(token, accountKey),
    onSuccess: (r) => {
      setNote(`⚠️ 已紧急熔断 · ${r.message}`)
      invalidate()
    },
    onError: () => setNote('熔断失败,请重试'),
  })

  const limitMut = useMutation({
    mutationFn: ({ accountKey, dailyLimit }: {
      accountKey: BinanceSquareAccountKey
      dailyLimit: number
    }) => updateAutoDailyLimit(token, accountKey, dailyLimit),
    onSuccess: (_s, value) => {
      setNote(`✓ ${value.accountKey === 'midas_trading' ? '点金雷达' : '点金 Midas'}每日配额已调整为 ${value.dailyLimit} 条`)
      invalidate()
    },
    onError: () => setNote('配额调整失败，请输入 1–50 的整数'),
  })

  // ★平台勾选(架子刀 · ADR 0050)· 白名单外(X)后端 400 拒,UI 也灰显不可点
  const platformMut = useMutation({
    mutationFn: ({ platform, checked, accountKey }: {
      platform: string
      checked: boolean
      accountKey: BinanceSquareAccountKey
    }) => toggleAutoPlatform(token, platform, checked, accountKey),
    onSuccess: (_s, v) => {
      setNote(v.checked ? `✓ 已勾选 ${PLATFORM_LABEL[v.platform] ?? v.platform} 自动发布` : `已取消 ${PLATFORM_LABEL[v.platform] ?? v.platform} 自动发布`)
      invalidate()
    },
    onError: (e) => setNote(e instanceof Error ? e.message : '平台勾选失败,请重试'),
  })

  const st = query.data
  const accounts = st?.accounts ?? []
  const runningCount = accounts.filter((account) => account.enabled && !account.circuit_open).length
  const circuitCount = accounts.filter((account) => account.circuit_open).length

  const onToggle = (accountKey: BinanceSquareAccountKey, isEnabled: boolean) => {
    if (!isEnabled) {
      const ok = window.confirm(
        '确定开启【全自动托管】?\n\n开启后系统将自动起草并发布推文到币安广场:\n' +
          '· 每 15 分钟一个发布机会，每小时最多 4 条、每日最多 40 条 · 仅 8:00-22:00 发\n· 新闻不足时自动回退热门波动币种分析\n· 门禁不通过的绝不发\n· 无需人工逐条审核\n\n' +
          '随时可用「紧急熔断」一键停止。确定开启?',
      )
      if (!ok) return
    }
    toggleMut.mutate({ enabled: !isEnabled, accountKey })
  }

  const onStop = (accountKey?: BinanceSquareAccountKey) => {
    const ok = window.confirm(
      '确定【紧急熔断】?\n\n将立刻:\n· 关闭自动托管开关\n· 开启熔断(停所有自动发)\n· 取消排队中的发布任务\n\n确定?',
    )
    if (ok) stopMut.mutate(accountKey)
  }

  return (
    <div className="mb-6 rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <span className="font-serif text-base font-bold">自动托管</span>
        {circuitCount > 0 ? (
          <span className="rounded bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
            ● {circuitCount} 个账号熔断
          </span>
        ) : runningCount > 0 ? (
          <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
            ● {runningCount} 个账号运行中
          </span>
        ) : (
          <span className="rounded bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            ● 已关闭
          </span>
        )}
        <span className="ml-auto text-[11px] text-muted-foreground">
          {query.isLoading ? '加载中…' : '每 15s 刷新'}
        </span>
      </div>

      {query.isError ? (
        <p className="text-sm text-muted-foreground">该面板仅管理员可见。</p>
      ) : (
        <>
          <div className="grid gap-3 lg:grid-cols-2">
            {(st?.accounts ?? []).map((account) => (
              <section key={account.account_key} className="rounded-md border border-paper p-3">
                <div className="mb-3 flex items-center gap-2">
                  <span className="font-medium">{account.display_name}</span>
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {account.content_profile === 'radar' ? '热点 + 行情' : 'K 线 + 结构'}
                  </span>
                  <span className={`ml-auto text-xs ${account.enabled ? 'text-green-700' : 'text-muted-foreground'}`}>
                    {account.circuit_open ? '● 已熔断' : account.enabled ? '● 运行中' : '● 已关闭'}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <StatChip label="今日配额" value={`${account.daily_used} / ${account.daily_limit}`} tone="text-gold" />
                  <StatChip label="发布错峰" value={`每 10 分钟 · +${account.slot_offset_minutes}分`} tone="text-foreground" />
                  <StatChip label="独立凭证" value={account.adapter_enabled ? '已配置' : '待配置'} tone={account.adapter_enabled ? 'text-green-700' : 'text-amber-700'} />
                </div>
                <div className="mt-3 grid grid-cols-5 gap-2 border-t border-paper pt-3">
                  <StatChip label="关注人数" value={compact(account.follower_count)} tone="text-foreground" />
                  <StatChip label="累计总阅读" value={compact(account.total_views)} tone="text-foreground" />
                  <StatChip label="近7日阅读" value={compact(account.views_7d)} tone="text-foreground" />
                  <StatChip label="近7日点赞" value={compact(account.likes_7d)} tone="text-foreground" />
                  <StatChip label="评论" value={compact(account.comments_7d)} tone="text-foreground" />
                </div>
                {account.last_error && (
                  <p className="mt-2 rounded bg-red-50 px-2 py-1.5 text-xs text-red-700">
                    连续 {account.failure_count}/3：{account.last_error}
                  </p>
                )}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <form
                    className="flex items-center gap-1.5"
                    onSubmit={(event) => {
                      event.preventDefault()
                      const value = Number(new FormData(event.currentTarget).get('daily_limit'))
                      limitMut.mutate({ accountKey: account.account_key, dailyLimit: value })
                    }}
                  >
                    <label htmlFor={`daily-limit-${account.account_key}`} className="text-xs">
                      每日上限
                    </label>
                    <input
                      id={`daily-limit-${account.account_key}`}
                      name="daily_limit"
                      type="number"
                      min={1}
                      max={50}
                      step={1}
                      required
                      defaultValue={account.daily_limit}
                      className="w-16 rounded border border-paper bg-background px-2 py-1 text-xs"
                    />
                    <button
                      type="submit"
                      disabled={limitMut.isPending}
                      className="rounded border border-paper px-2.5 py-1 text-xs disabled:opacity-40"
                    >
                      保存
                    </button>
                  </form>
                  <label className="flex items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      checked={account.checked}
                      disabled={!account.adapter_enabled || platformMut.isPending}
                      onChange={(event) => platformMut.mutate({
                        platform: 'binance_square',
                        checked: event.target.checked,
                        accountKey: account.account_key,
                      })}
                      className="accent-midas-red"
                    />
                    允许自动发布
                  </label>
                  <button
                    type="button"
                    onClick={() => onToggle(account.account_key, account.enabled)}
                    disabled={!account.checked || toggleMut.isPending}
                    className="rounded bg-midas-red px-2.5 py-1 text-xs text-white disabled:opacity-40"
                  >
                    {account.enabled ? '关闭' : '开启'}此账号
                  </button>
                  <button
                    type="button"
                    onClick={() => onStop(account.account_key)}
                    disabled={stopMut.isPending}
                    className="rounded border border-red-200 px-2.5 py-1 text-xs text-red-700"
                  >
                    熔断此账号
                  </button>
                </div>
              </section>
            ))}
          </div>

          <div className="mt-4 border-t border-paper pt-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] text-muted-foreground">内容数据源</span>
              <span className="text-[11px] text-muted-foreground">各源独立运行，单源异常不阻塞发布</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {(st?.sources ?? []).map((source) => {
                const status = SOURCE_STATUS[source.status]
                const detail = source.last_error
                  ? `${source.last_error} · ${source.latency_ms}ms`
                  : `本轮新增 ${source.last_inserted} 条 · ${source.latency_ms}ms`
                return (
                  <span
                    key={source.source}
                    title={detail}
                    className={`rounded-md border px-2 py-1 text-[11px] ${status.className}`}
                  >
                    {source.source} · {status.label}
                  </span>
                )
              })}
              {(st?.sources ?? []).length === 0 && (
                <span className="text-xs text-muted-foreground">等待首次采集结果…</span>
              )}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-paper pt-3">
            <button
              type="button"
              onClick={() => onStop()}
              disabled={stopMut.isPending || token === ''}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              {stopMut.isPending ? '熔断中…' : '🛑 紧急熔断'}
            </button>
            {circuitCount > 0 && (
              <span className="text-xs text-red-600">
                熔断账号可在上方账号卡片中重新开启
              </span>
            )}
          </div>

          {note && (
            <p className="mt-3 rounded-md bg-gold/10 px-3 py-2 text-xs text-muted-foreground">
              {note}
            </p>
          )}
        </>
      )}
    </div>
  )
}
