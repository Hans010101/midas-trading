'use client'

/**
 * 管理员 · 周报全自动发送(上传成品 PDF+md → 解析预览 → 定时/补传发送)。
 *
 * ★ 安全边界后端 AdminDep(403)· 数据全来自 admin API,普通用户手输 URL → 后端 403 → 降级。
 * 流程:运营在外部做好成品周报(PDF 精排 + md 结构化)→ 这里传两份 → 系统提取 md 填邮件模板 →
 *   ★人工点「计划发送」(等周日21:00定时发)/「立即发送」(当场发)·「取消计划」可21:00前撤回。
 *   ★上传不再自动发送、不再有补救窗口自动发(发送由人工确认闸门控制)。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useRef, useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import {
  AdminApiError,
  cancelWeeklyDispatchSchedule,
  fetchWeeklyDispatches,
  scheduleWeeklyDispatch,
  sendWeeklyDispatchNow,
  uploadWeeklyDispatch,
  type WeeklyDispatchItem,
  type WeeklyUploadResult,
} from '@/lib/api/admin'

const STATUS_LABEL: Record<string, string> = {
  uploaded: '待发送(未计划)',
  scheduled: '已计划', // 实际展示拼上动态日期(见 statusText)· 此为兜底
  sent: '已发送',
}

/** scheduled 状态拼上「下一个周日 21:00」的具体日期(M月D日21:00 · 后端 CST 算)。 */
function statusText(status: string, nextSendLabel: string): string {
  if (status === 'scheduled') return `已计划 · ${nextSendLabel}发送`
  return STATUS_LABEL[status] ?? status
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? (v as string[]) : []
}

function errDetail(e: unknown): string {
  return e instanceof AdminApiError ? e.detail : '请重试'
}

export default function AdminWeeklyDispatchPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()
  const pdfRef = useRef<HTMLInputElement>(null)
  const mdRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<WeeklyUploadResult | null>(null)
  const [confirmSendId, setConfirmSendId] = useState<number | null>(null) // ★立即发送二次确认

  const query = useQuery({
    queryKey: ['admin-weekly-dispatch'],
    queryFn: ({ signal }) => fetchWeeklyDispatches(token, signal),
    enabled: token !== '',
  })

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['admin-weekly-dispatch'] })

  const uploadMut = useMutation({
    mutationFn: () => {
      const pdf = pdfRef.current?.files?.[0]
      const md = mdRef.current?.files?.[0]
      if (!pdf || !md) throw new Error('请同时选择 PDF 和 md 文件')
      return uploadWeeklyDispatch(token, pdf, md)
    },
    onSuccess: (res) => {
      setPreview(res)
      invalidate()
    },
  })

  const scheduleMut = useMutation({
    mutationFn: (id: number) => scheduleWeeklyDispatch(token, id),
    onSuccess: invalidate,
  })
  const cancelMut = useMutation({
    mutationFn: (id: number) => cancelWeeklyDispatchSchedule(token, id),
    onSuccess: invalidate,
  })
  const sendMut = useMutation({
    mutationFn: (id: number) => sendWeeklyDispatchNow(token, id),
    onSuccess: () => {
      setConfirmSendId(null)
      invalidate()
    },
  })

  const forbidden = query.error instanceof AdminApiError && query.error.status === 403
  const items: WeeklyDispatchItem[] = query.data?.items ?? []
  const nextSendLabel: string = query.data?.next_send_label ?? '周日21:00'

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-5xl px-6 py-8">
        <h1 className="mb-4 font-serif text-xl font-bold">周报发送</h1>
        <AdminNav />

        {forbidden ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center shadow-sm">
            <p className="text-sm text-muted-foreground">该页面仅管理员可见。</p>
            <Link
              href="/global"
              className="mt-3 inline-block rounded-md bg-midas-red px-4 py-1.5 text-sm text-white hover:bg-midas-red/90"
            >
              返回首页
            </Link>
          </div>
        ) : (
          <>
            {/* 上传成品 */}
            <section className="mb-6 rounded-lg border border-paper bg-cream p-5 shadow-sm">
              <h2 className="mb-2 font-serif text-base font-bold">上传本周成品周报</h2>
              <p className="mb-4 text-xs text-muted-foreground">
                上传外部做好的两份同步文件:① PDF(精排版作邮件附件)② md(按约定结构,系统提取填邮件正文)。
                上传后到下方点「计划发送」(等下一个周日 21:00 定时发)或「立即发送」(当场发给订阅用户)。
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-sm">
                  <span className="mb-1 block text-xs text-muted-foreground">PDF 附件</span>
                  <input ref={pdfRef} type="file" accept=".pdf" className="block w-full text-xs" />
                </label>
                <label className="text-sm">
                  <span className="mb-1 block text-xs text-muted-foreground">md 结构化</span>
                  <input ref={mdRef} type="file" accept=".md,.markdown,.txt" className="block w-full text-xs" />
                </label>
              </div>
              <button
                type="button"
                onClick={() => uploadMut.mutate()}
                disabled={uploadMut.isPending}
                className="mt-4 rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:opacity-50"
              >
                {uploadMut.isPending ? '上传解析中…' : '上传并解析'}
              </button>
              {uploadMut.isError && (
                <p className="mt-2 text-xs text-midas-red">
                  上传失败:
                  {uploadMut.error instanceof AdminApiError
                    ? uploadMut.error.detail
                    : uploadMut.error instanceof Error
                      ? uploadMut.error.message
                      : '请重试'}
                </p>
              )}
            </section>

            {/* 解析预览 + 邮件预览 */}
            {preview && (
              <section className="mb-6 rounded-lg border border-gold/40 bg-gold/5 p-5 shadow-sm">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="font-serif text-base font-bold">
                    解析预览 · {preview.year} 第 {preview.week} 周
                  </h2>
                  <span className="text-xs text-muted-foreground">
                    状态:{STATUS_LABEL[preview.status] ?? preview.status} · 去下方列表点「计划发送」或「立即发送」
                  </span>
                </div>
                {preview.missing.length > 0 && (
                  <p className="mb-3 rounded bg-midas-red-glow/40 px-2 py-1 text-xs text-midas-red">
                    ⚠ 缺失模块(邮件对应区将为空):{preview.missing.join('、')}
                  </p>
                )}
                <div className="mb-3 grid gap-2 text-xs sm:grid-cols-2">
                  <Field label="一句话导语" value={String(preview.extracted.lead ?? '—')} />
                  <Field
                    label="核心结论"
                    value={`${strList(preview.extracted.conclusions).length} 条`}
                  />
                  <Field label="走强" value={strList(preview.extracted.strong).join('、') || '—'} />
                  <Field label="走弱" value={strList(preview.extracted.weak).join('、') || '—'} />
                  <Field
                    label="下周关注"
                    value={`${strList(preview.extracted.next_week).length} 条`}
                  />
                  <Field label="PDF 附件" value={preview.pdf_filename} />
                </div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">邮件预览</p>
                <iframe
                  title="邮件预览"
                  srcDoc={preview.email_html}
                  className="h-[460px] w-full rounded border border-paper bg-white"
                />
              </section>
            )}

            {/* 投递列表 */}
            <section className="rounded-lg border border-paper bg-cream shadow-sm">
              <div className="border-b border-paper px-4 py-2 text-xs font-medium text-muted-foreground">
                历史投递
              </div>
              {items.length === 0 ? (
                <p className="p-6 text-center text-xs text-muted-foreground/70">
                  暂无周报投递。上传本周成品试试。
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-paper text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2 font-medium">周次</th>
                      <th className="px-4 py-2 font-medium">标题</th>
                      <th className="px-4 py-2 font-medium">状态</th>
                      <th className="px-4 py-2 font-medium">上传</th>
                      <th className="px-4 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => (
                      <tr key={it.id} className="border-b border-paper/60 last:border-0">
                        <td className="px-4 py-3 font-mono text-xs">
                          {it.year} W{it.week}
                        </td>
                        <td className="px-4 py-3 text-foreground">{it.title}</td>
                        <td className="px-4 py-3">
                          <span
                            className={
                              it.status === 'sent'
                                ? 'text-gold'
                                : it.status === 'scheduled'
                                  ? 'text-midas-red'
                                  : 'text-muted-foreground'
                            }
                          >
                            {statusText(it.status, nextSendLabel)}
                            {it.status === 'sent' && it.sent_at
                              ? ` · ${it.sent_at.slice(5, 16).replace('T', ' ')}`
                              : ''}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                          {it.uploaded_at.slice(5, 16).replace('T', ' ')}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex justify-end gap-1.5">
                            {it.status === 'uploaded' && (
                              <button
                                type="button"
                                onClick={() => scheduleMut.mutate(it.id)}
                                disabled={scheduleMut.isPending}
                                className="rounded bg-midas-red px-2.5 py-1 text-xs font-medium text-white hover:bg-midas-red-deep disabled:opacity-50"
                              >
                                计划发送
                              </button>
                            )}
                            {it.status === 'scheduled' && (
                              <button
                                type="button"
                                onClick={() => cancelMut.mutate(it.id)}
                                disabled={cancelMut.isPending}
                                className="rounded border border-paper px-2.5 py-1 text-xs text-muted-foreground hover:bg-paper/50 disabled:opacity-50"
                              >
                                取消计划
                              </button>
                            )}
                            {it.status !== 'sent' && (
                              <button
                                type="button"
                                onClick={() => setConfirmSendId(it.id)}
                                className="rounded border border-midas-red px-2.5 py-1 text-xs text-midas-red hover:bg-midas-red-glow/40"
                              >
                                立即发送
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {(scheduleMut.error ?? cancelMut.error ?? sendMut.error) && (
                <p className="px-4 py-2 text-xs text-midas-red">
                  操作失败:
                  {errDetail(scheduleMut.error ?? cancelMut.error ?? sendMut.error)}
                </p>
              )}
            </section>
          </>
        )}

        {/* ★立即发送二次确认 */}
        {confirmSendId !== null && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-sm rounded-lg border border-paper bg-cream p-5 shadow-xl">
              <h3 className="mb-2 font-serif text-base font-bold text-foreground">立即发送?</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                确定立即发送给所有订阅周报的用户?此操作不可撤销。
              </p>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmSendId(null)}
                  className="rounded-md border border-paper px-4 py-1.5 text-sm text-muted-foreground hover:bg-paper/50"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => sendMut.mutate(confirmSendId)}
                  disabled={sendMut.isPending}
                  className="rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white hover:bg-midas-red-deep disabled:opacity-50"
                >
                  {sendMut.isPending ? '发送中…' : '确认发送'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-paper bg-background px-2 py-1">
      <span className="text-muted-foreground">{label}:</span>{' '}
      <span className="text-foreground">{value}</span>
    </div>
  )
}
