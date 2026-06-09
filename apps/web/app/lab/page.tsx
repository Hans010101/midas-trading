'use client'

/**
 * 策略研究室 · 回测列表 + 发起(P1-4d · ADR 0038)。
 *
 * 骨架照 app/crypto-market/page.tsx:'use client' + TopNav + main 容器 + 行内状态机。
 * 🔴 红线:回测纯虚拟研究 · market 锁 crypto perp(不可改)· 绝不下单 / 撮合 / 真实交易。
 * ⛔ 隐藏路由:不挂全局导航,内部可见。
 */

import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useState, type ReactNode } from 'react'

import { TopNav } from '@/components/layout/top-nav'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { useBacktestList, useCreateBacktest } from '@/hooks/use-backtest'
import type { BacktestStatus } from '@/lib/api/backtest'

const STATUS_LABEL: Record<BacktestStatus, string> = {
  pending: '进行中',
  done: '完成',
  error: '失败',
}

const PAGE_SIZE = 10 // 列表每页条数(纯前端切片分页 · 后端 limit 50 已够覆盖,不碰后端)

export default function LabPage() {
  const router = useRouter()
  const { status: authStatus } = useSession()
  const list = useBacktestList()
  const create = useCreateBacktest()

  const [symbol, setSymbol] = useState('BTCUSDT')
  const [start, setStart] = useState('2025-01-17')
  const [end, setEnd] = useState('2026-05-31')
  const [smaFast, setSmaFast] = useState(5)
  const [smaSlow, setSmaSlow] = useState(20)
  const [page, setPage] = useState(1)

  // 前端切片分页(数据已由 useBacktestList 一次取回 ≤50 条)· currentPage 夹取防越界
  const rows = list.data ?? []
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageRows = rows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  function submit() {
    create.mutate(
      {
        symbol: symbol.trim().toUpperCase(),
        start,
        end,
        market: 'crypto', // 红线:锁 crypto perp,不从表单取
        period: '1d',
        sma_fast: smaFast,
        sma_slow: smaSlow,
      },
      { onSuccess: (data) => router.push(`/lab/report?id=${data.id}`) },
    )
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="mx-auto w-full max-w-5xl px-6 py-8">
        <div className="mb-6 flex items-center gap-3">
          <h1 className="font-serif text-2xl font-bold">策略研究室 · 回测</h1>
        </div>

        {authStatus === 'unauthenticated' ? (
          <EmptyState title="请先登录" hint="研究室回测需要登录后访问" />
        ) : (
          <>
            {/* ── 发起表单 ──────────────────────────────────────────── */}
            <section className="mb-10 rounded-lg border border-paper bg-cream p-5 shadow-sm">
              <h2 className="mb-4 font-serif text-lg font-bold">发起回测</h2>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <Field label="标的(crypto perp)">
                  <Input
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    placeholder="BTCUSDT"
                  />
                </Field>
                <Field label="市场(锁定)">
                  <Input
                    value="crypto perp"
                    disabled
                    readOnly
                    className="cursor-not-allowed bg-surface-subtle text-muted-foreground"
                  />
                </Field>
                <Field label="周期(锁定)">
                  <Input
                    value="1d · 日线"
                    disabled
                    readOnly
                    className="cursor-not-allowed bg-surface-subtle text-muted-foreground"
                  />
                </Field>
                <Field label="开始日期">
                  <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
                </Field>
                <Field label="结束日期">
                  <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="SMA 快线">
                    <Input
                      type="number"
                      min={1}
                      value={smaFast}
                      onChange={(e) => setSmaFast(Number(e.target.value))}
                    />
                  </Field>
                  <Field label="SMA 慢线">
                    <Input
                      type="number"
                      min={1}
                      value={smaSlow}
                      onChange={(e) => setSmaSlow(Number(e.target.value))}
                    />
                  </Field>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-3">
                <Button onClick={submit} disabled={create.isPending || symbol.trim() === ''}>
                  {create.isPending ? '发起中…' : '发起回测(虚拟)'}
                </Button>
                {create.isError && (
                  <span className="text-sm text-midas-red">{create.error.message}</span>
                )}
              </div>
              <p className="mt-3 text-xs text-faint">
                策略 = SMA 双均线交叉(确定性 · 零 LLM)· 数据只读 ClickHouse。
              </p>
            </section>

            {/* ── 我的回测列表 ──────────────────────────────────────── */}
            <section>
              <h2 className="mb-3 font-serif text-lg font-bold">我的回测</h2>
              {list.isPending ? (
                <LoadingNote className="py-12" />
              ) : list.isError ? (
                <EmptyState title="暂时无法读取" hint="后端不可达 · 稍后重试" />
              ) : rows.length === 0 ? (
                <EmptyState icon="🧪" title="还没有回测" hint="用上方表单发起第一个" />
              ) : (
                <>
                  <div className="overflow-x-auto rounded-lg border border-paper">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-paper bg-surface-card text-xs text-muted-foreground">
                          <th className="px-3 py-2 text-left font-medium">#</th>
                          <th className="px-3 py-2 text-left font-medium">标的</th>
                          <th className="px-3 py-2 text-left font-medium">区间</th>
                          <th className="px-3 py-2 text-left font-medium">状态</th>
                          <th className="px-3 py-2 text-left font-medium">创建时间</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pageRows.map((r) => (
                          <tr
                            key={r.id}
                            onClick={() => router.push(`/lab/report?id=${r.id}`)}
                            className="cursor-pointer border-b border-paper/60 transition-colors hover:bg-midas-red-glow/30"
                          >
                            <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground/70">
                              {r.id}
                            </td>
                            <td className="px-3 py-2.5 font-mono font-bold">{r.symbol}</td>
                            <td className="px-3 py-2.5 text-xs text-muted-foreground">
                              {r.start_date} → {r.end_date}
                            </td>
                            <td className="px-3 py-2.5">
                              <StatusBadge status={r.status} />
                            </td>
                            <td className="px-3 py-2.5 text-xs text-muted-foreground">
                              {new Date(r.created_at).toLocaleString('zh-CN')}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {totalPages > 1 && (
                    <div className="mt-4 flex items-center justify-center gap-4">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={currentPage <= 1}
                        onClick={() => setPage(currentPage - 1)}
                      >
                        上一页
                      </Button>
                      <span className="font-mono text-xs text-muted-foreground">
                        第 {currentPage} / {totalPages} 页
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={currentPage >= totalPages}
                        onClick={() => setPage(currentPage + 1)}
                      >
                        下一页
                      </Button>
                    </div>
                  )}
                </>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

function StatusBadge({ status }: { status: BacktestStatus }) {
  const cls =
    status === 'done'
      ? 'bg-success/10 text-success'
      : status === 'error'
        ? 'bg-midas-red/10 text-midas-red'
        : 'bg-gold/15 text-gold'
  return (
    <span className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${cls}`}>
      {STATUS_LABEL[status]}
    </span>
  )
}
