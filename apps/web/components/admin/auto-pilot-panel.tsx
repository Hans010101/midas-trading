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
} from '@/lib/api/x-auto'

// 平台标识 → 显示名(加平台 = registry 加一行后,这里补个显示名即可;缺省显示原标识)
const PLATFORM_LABEL: Record<string, string> = {
  binance_square: '币安广场',
  x: '𝕏(Twitter)',
}

function StatChip({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className={`text-sm font-medium ${tone}`}>{value}</span>
    </div>
  )
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
    mutationFn: (enabled: boolean) => toggleAutoPilot(token, enabled),
    onSuccess: (s) => {
      setNote(s.enabled ? '✓ 自动托管已开启 · 系统将按守卫自动起草并发布' : '自动托管已关闭')
      invalidate()
    },
    onError: () => setNote('操作失败,请重试'),
  })

  const stopMut = useMutation({
    mutationFn: () => stopAutoPilot(token),
    onSuccess: (r) => {
      setNote(`⚠️ 已紧急熔断 · ${r.message}`)
      invalidate()
    },
    onError: () => setNote('熔断失败,请重试'),
  })

  // ★平台勾选(架子刀 · ADR 0050)· 白名单外(X)后端 400 拒,UI 也灰显不可点
  const platformMut = useMutation({
    mutationFn: ({ platform, checked }: { platform: string; checked: boolean }) =>
      toggleAutoPlatform(token, platform, checked),
    onSuccess: (_s, v) => {
      setNote(v.checked ? `✓ 已勾选 ${PLATFORM_LABEL[v.platform] ?? v.platform} 自动发布` : `已取消 ${PLATFORM_LABEL[v.platform] ?? v.platform} 自动发布`)
      invalidate()
    },
    onError: (e) => setNote(e instanceof Error ? e.message : '平台勾选失败,请重试'),
  })

  const st = query.data
  const enabled = st?.enabled ?? false
  const circuitOpen = st?.circuit_open ?? false

  const onToggle = () => {
    if (!enabled) {
      const ok = window.confirm(
        '确定开启【全自动托管】?\n\n开启后系统将自动起草并发布推文到币安广场:\n' +
          '· 每 20 分钟一个发布机会，每日最多 40 条 · 仅 8:00-22:00 发\n· 新闻不足时自动回退热门波动币种分析\n· 门禁不通过的绝不发\n· 无需人工逐条审核\n\n' +
          '随时可用「紧急熔断」一键停止。确定开启?',
      )
      if (!ok) return
    }
    toggleMut.mutate(!enabled)
  }

  const onStop = () => {
    const ok = window.confirm(
      '确定【紧急熔断】?\n\n将立刻:\n· 关闭自动托管开关\n· 开启熔断(停所有自动发)\n· 取消排队中的发布任务\n\n确定?',
    )
    if (ok) stopMut.mutate()
  }

  return (
    <div className="mb-6 rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <span className="font-serif text-base font-bold">自动托管</span>
        {circuitOpen ? (
          <span className="rounded bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
            ● 熔断中
          </span>
        ) : enabled ? (
          <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
            ● 运行中
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
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatChip
              label="总开关"
              value={enabled ? '开启' : '关闭'}
              tone={enabled ? 'text-green-700' : 'text-muted-foreground'}
            />
            <StatChip
              label="熔断"
              value={circuitOpen ? '已熔断' : '正常'}
              tone={circuitOpen ? 'text-red-700' : 'text-foreground'}
            />
            <StatChip
              label="今日配额"
              value={st ? `${st.daily_used} / ${st.daily_used + st.daily_remaining}` : '—'}
              tone="text-gold"
            />
            <StatChip
              label="发布时段"
              value={st ? (st.in_window ? '在窗(8:00-22:00)' : '不在窗') : '—'}
              tone={st?.in_window ? 'text-foreground' : 'text-muted-foreground'}
            />
          </div>

          {st?.last_error && (
            <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              最近失败（连续 {st.failure_count}/3）：{st.last_error}
            </p>
          )}

          {/* ★平台多选(架子刀 · ADR 0050):勾选的平台才自动质检发布 · 总开关 AND 平台勾选双闸。
              X 灰显「暂未启用」= auto_publish 白名单物理焊死(后端 400 双保险),待 Hans 验质量授权。 */}
          <div className="mt-4 border-t border-paper pt-3">
            <span className="text-[11px] text-muted-foreground">自动发布平台</span>
            <div className="mt-1.5 flex flex-wrap items-center gap-4">
              {(st?.platforms ?? []).map((p) => (
                <label
                  key={p.platform}
                  className={`flex items-center gap-1.5 text-sm ${
                    p.auto_allowed ? 'cursor-pointer text-foreground' : 'cursor-not-allowed text-muted-foreground'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={p.checked}
                    disabled={!p.auto_allowed || platformMut.isPending || token === ''}
                    onChange={(e) =>
                      platformMut.mutate({ platform: p.platform, checked: e.target.checked })
                    }
                    className="h-3.5 w-3.5 accent-midas-red disabled:cursor-not-allowed"
                  />
                  {PLATFORM_LABEL[p.platform] ?? p.platform}
                  {!p.auto_allowed && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                      暂未启用
                    </span>
                  )}
                  {p.auto_allowed && !p.adapter_enabled && (
                    <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-700">
                      未配 API Key
                    </span>
                  )}
                </label>
              ))}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-paper pt-3">
            <button
              type="button"
              onClick={onToggle}
              disabled={toggleMut.isPending || token === ''}
              className={
                enabled
                  ? 'rounded-md border border-paper px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground disabled:opacity-50'
                  : 'rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white hover:bg-midas-red/90 disabled:opacity-50'
              }
            >
              {toggleMut.isPending ? '处理中…' : enabled ? '关闭自动托管' : '开启自动托管'}
            </button>
            <button
              type="button"
              onClick={onStop}
              disabled={stopMut.isPending || token === ''}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              {stopMut.isPending ? '熔断中…' : '🛑 紧急熔断'}
            </button>
            {circuitOpen && (
              <span className="text-xs text-red-600">
                熔断中 · 重新「开启自动托管」会自动清熔断
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
