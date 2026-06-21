'use client'

/**
 * 周报素材管理(第三刀)· admin 报告页内嵌 · 上传 md/PDF → 提取文本注入本期生成。
 *
 * ★ 安全边界后端 AdminDep(403)· 403 时返回 null(由报告列表页统一降级)。
 * ★ 上传 multipart 不手设 Content-Type(浏览器带 boundary)· 7 天后自动清理(后端 beat + OSS lifecycle)。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { useRef, useState } from 'react'

import {
  AdminApiError,
  deleteAdminMaterial,
  fetchAdminMaterials,
  uploadAdminMaterial,
} from '@/lib/api/admin'

export function ReportMaterialsPanel() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [err, setErr] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['admin-materials'],
    queryFn: ({ signal }) => fetchAdminMaterials(token, signal),
    enabled: token !== '',
  })

  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadAdminMaterial(token, file),
    onSuccess: () => {
      setErr(null)
      void qc.invalidateQueries({ queryKey: ['admin-materials'] })
    },
    onError: (e) => setErr(e instanceof AdminApiError ? e.detail : '上传失败'),
  })

  const delMut = useMutation({
    mutationFn: (id: number) => deleteAdminMaterial(token, id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['admin-materials'] }),
  })

  // 403 → 不渲染(报告列表页已统一降级提示)
  if (query.error instanceof AdminApiError && query.error.status === 403) return null

  const data = query.data
  const items = data?.items ?? []

  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) uploadMut.mutate(file)
    if (fileRef.current) fileRef.current.value = '' // 允许重复选同名文件
  }

  return (
    <section className="mb-6 rounded-lg border border-paper bg-cream p-5 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-serif text-base font-bold">
          本期素材
          {data?.period_start && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {data.period_start} ~ {data.period_end}
            </span>
          )}
        </h2>
        <div>
          <input
            ref={fileRef}
            id="material-file"
            type="file"
            accept=".md,.markdown,.txt,.pdf"
            onChange={onPick}
            className="hidden"
          />
          <label
            htmlFor="material-file"
            className="cursor-pointer rounded-md border border-midas-red px-3 py-1.5 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow/40"
          >
            {uploadMut.isPending ? '上传中…' : '+ 上传素材(md / PDF)'}
          </label>
        </div>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        运营搜集的外部素材(md / PDF)· 上传即提取文本,生成本期周报时作参考注入 · 7 天后自动清理。
      </p>

      {err && <p className="mb-2 text-xs text-midas-red">上传失败:{err}</p>}

      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground/70">本期暂无素材。上传后将参与本期周报生成。</p>
      ) : (
        <ul className="divide-y divide-paper/60">
          {items.map((m) => (
            <li key={m.id} className="flex items-center justify-between py-2 text-sm">
              <span className="flex min-w-0 items-center gap-2">
                <span className="rounded bg-paper/60 px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                  {m.content_type}
                </span>
                <span className="truncate text-foreground">{m.filename}</span>
                <span className="shrink-0 text-xs text-muted-foreground">· {m.char_count} 字</span>
              </span>
              <button
                type="button"
                onClick={() => delMut.mutate(m.id)}
                disabled={delMut.isPending}
                className="shrink-0 text-xs text-midas-red transition-opacity hover:opacity-80 disabled:opacity-50"
              >
                删除
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
