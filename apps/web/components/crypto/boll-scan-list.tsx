'use client'

/**
 * 布林做T结构信号列表(做T A-2)· 只读 A-1 的 /crypto/boll-scan 快照。
 *
 * 纯展示 · 不碰交易。结构倾向用涨跌色偏好(偏多=text-up / 偏空=text-down / 中性=muted),
 * 复用 --color-up/--color-down(data-color-pref 翻转),★绝不写死红绿。
 * ★底部强制展示接口返回的 disclaimer(红线)。无快照(count=0)友好空态,不报错。
 */

import { useMemo, useState } from 'react'

import { fetchBollScan } from '@/lib/api/crypto-market'
import { cn } from '@/lib/utils'
import { useQuery } from '@tanstack/react-query'

function fmtPrice(n: number): string {
  if (n >= 1) return n.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return n.toFixed(4)
}
function fmtPct(n: number | null): string {
  if (n == null) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}
// %B 位置标注 · 本地从 pct_b 派生(对齐后端 boll_state 阈值 0.8 / 0.2 / 0.4~0.6)· 导出供单测
export function pctbZone(b: number): string {
  if (b > 0.8) return '近上轨'
  if (b < 0.2) return '近下轨'
  if (b >= 0.4 && b <= 0.6) return '近中轨'
  return '中间'
}
// ★结构倾向配色:复用涨跌色偏好(text-up/down → var(--color-up/down)),不写死红绿 · 导出供单测
export function biasTone(bias: string): string {
  if (bias === '偏多') return 'text-up'
  if (bias === '偏空') return 'text-down'
  return 'text-muted-foreground'
}

type BiasFilter = 'all' | '偏多' | '偏空' | '中性'
const BIAS_TABS: BiasFilter[] = ['all', '偏多', '偏空', '中性']

export function BollScanList({
  onSymbolClick,
}: {
  onSymbolClick?: (binanceSymbol: string) => void
}) {
  const [bias, setBias] = useState<BiasFilter>('all')
  const [onlyTransition, setOnlyTransition] = useState(false)

  const q = useQuery({
    queryKey: ['crypto-boll-scan'],
    queryFn: ({ signal }) => fetchBollScan(signal),
    retry: 0,
    staleTime: 60_000,
  })

  const items = useMemo(() => {
    const all = q.data?.items ?? []
    return all.filter(
      (it) => (bias === 'all' || it.bias === bias) && (!onlyTransition || it.transition),
    )
  }, [q.data, bias, onlyTransition])

  // 免责优先用接口返回值(红线口径由后端锁死)· 兜底常量防接口异常时丢免责
  const disclaimer = q.data?.disclaimer ?? '结构描述非建议 · 仅供参考,不构成投资建议'

  return (
    <div>
      {/* 筛选条:倾向 tab + 只看转换 + 快照时间 */}
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        {BIAS_TABS.map((b) => (
          <button
            key={b}
            type="button"
            onClick={() => setBias(b)}
            className={cn(
              'rounded-md border px-2.5 py-1 transition-colors',
              bias === b
                ? 'border-midas-red bg-midas-red-glow/30 text-midas-red'
                : 'border-paper text-muted-foreground hover:border-midas-red/50',
            )}
          >
            {b === 'all' ? '全部' : b}
          </button>
        ))}
        <label className="ml-1 flex cursor-pointer items-center gap-1.5 text-muted-foreground">
          <input
            type="checkbox"
            checked={onlyTransition}
            onChange={(e) => setOnlyTransition(e.target.checked)}
          />
          只看本轮转换
        </label>
        {q.data?.as_of && (
          <span className="ml-auto text-muted-foreground/60">
            快照{' '}
            {new Date(q.data.as_of).toLocaleTimeString('zh-CN', {
              hour: '2-digit',
              minute: '2-digit',
            })}{' '}
            · 共 {items.length}
          </span>
        )}
      </div>

      {/* 表格 */}
      <div className="overflow-x-auto rounded-lg border border-paper">
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-paper bg-surface-card text-xs text-muted-foreground">
              <th className="w-12 px-3 py-2 text-center font-medium">#</th>
              <th className="px-3 py-2 text-left font-medium">交易对</th>
              <th className="px-3 py-2 text-right font-medium">最新价</th>
              <th className="px-3 py-2 text-left font-medium">布林状态</th>
              <th className="px-3 py-2 text-center font-medium">结构倾向</th>
              <th className="px-3 py-2 text-right font-medium" title="%B = (收盘−下轨)/(上轨−下轨)">%B</th>
              <th className="px-3 py-2 text-left font-medium">状态转换</th>
              <th className="px-3 py-2 text-right font-medium">24H 涨跌%</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {q.isPending && <StateRow text="载入中…" />}
            {q.isError && <StateRow text="暂时无法读取做T信号(后端不可达)" />}
            {q.isSuccess && items.length === 0 && (
              <StateRow text={q.data.count === 0 ? '暂无做T信号 · 待下一轮扫描' : '无匹配信号 · 调整筛选'} />
            )}
            {q.isSuccess &&
              items.map((it, i) => (
                <tr
                  key={it.symbol}
                  onClick={() => onSymbolClick?.(it.symbol)}
                  title="点击在新标签打开详情页"
                  className="group cursor-pointer border-b border-paper/60 transition-colors hover:bg-midas-red-glow/30"
                >
                  <td className="px-3 py-2.5 text-center font-mono text-xs text-muted-foreground/70">
                    {i + 1}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="font-serif font-bold text-foreground">{it.symbol}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono">{fmtPrice(it.close)}</td>
                  <td className="px-3 py-2.5 text-left text-muted-foreground/90">{it.state_label}</td>
                  <td className={cn('px-3 py-2.5 text-center font-medium', biasTone(it.bias))}>
                    {it.bias}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono">
                    {it.pct_b.toFixed(2)}
                    <span className="ml-1 text-[11px] text-muted-foreground/60">
                      {pctbZone(it.pct_b)}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-left text-xs">
                    {it.transition && it.transition_from ? (
                      <span className="inline-flex items-center gap-1">
                        <span className="rounded bg-midas-red-glow/50 px-1.5 py-0.5 text-[10px] font-medium text-midas-red">
                          刚转换
                        </span>
                        <span className="text-muted-foreground/70">
                          {it.transition_from}→{it.state_label}
                        </span>
                      </span>
                    ) : (
                      <span className="text-muted-foreground/30">—</span>
                    )}
                  </td>
                  <td
                    className={cn(
                      'px-3 py-2.5 text-right font-mono',
                      it.change_pct_24h == null
                        ? 'text-muted-foreground/40'
                        : it.change_pct_24h >= 0
                          ? 'text-up'
                          : 'text-down',
                    )}
                  >
                    {fmtPct(it.change_pct_24h)}
                  </td>
                  <td className="px-2 text-center text-muted-foreground/30 transition-colors group-hover:text-midas-red">
                    ›
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* ★底部免责(红线 · 接口返回的 disclaimer · 必须显示)*/}
      <p className="mt-4 text-center text-xs text-muted-foreground/70">{disclaimer}</p>
    </div>
  )
}

function StateRow({ text }: { text: string }) {
  return (
    <tr>
      <td colSpan={9} className="px-3 py-10 text-center text-sm text-muted-foreground/60">
        {text}
      </td>
    </tr>
  )
}
