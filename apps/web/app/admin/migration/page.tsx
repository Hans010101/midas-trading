'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import {
  fetchMigrationStatus,
  importLegacyUsers,
  type MigrationImportResult,
} from '@/lib/api/admin'

const SAMPLE = JSON.stringify({
  source_revision: 'legacy-export-YYYYMMDD',
  users: [{
    legacy_user_id: 'old-user-id',
    email: 'user@example.com',
    display_name: 'User',
  }],
}, null, 2)

export default function MigrationCenterPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const queryClient = useQueryClient()
  const [payloadText, setPayloadText] = useState(SAMPLE)
  const [preview, setPreview] = useState<MigrationImportResult | null>(null)
  const status = useQuery({
    queryKey: ['admin-migration-status'],
    queryFn: ({ signal }) => fetchMigrationStatus(token, signal),
    enabled: token !== '',
  })
  const mutation = useMutation({
    mutationFn: (dryRun: boolean) => {
      const parsed = JSON.parse(payloadText) as Record<string, unknown>
      return importLegacyUsers(token, parsed, dryRun)
    },
    onSuccess: (result) => {
      setPreview(result)
      void queryClient.invalidateQueries({ queryKey: ['admin-migration-status'] })
    },
  })
  const canCommit = preview?.dry_run === true && (preview.conflicts?.length ?? 0) === 0
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <AdminNav />
        <h1 className="font-serif text-xl font-bold">用户迁移中心</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          最小批次只需旧用户 ID 与邮箱。Google 用户切换后用原邮箱登录即可自动绑定，无需重新注册；收藏、提醒和模拟交易记录均为可选数据。
        </p>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {Object.entries(status.data?.cloudflare_counts ?? {}).map(([key, value]) => (
            <section key={key} className="rounded-lg border border-paper bg-cream p-4">
              <p className="text-xs text-muted-foreground">{key}</p>
              <p className="mt-1 font-mono text-2xl font-bold">{value}</p>
            </section>
          ))}
        </div>
        <section className="mt-5 rounded-lg border border-paper bg-cream p-5">
          <label htmlFor="migration-payload" className="text-sm font-medium">旧系统导出批次（JSON）</label>
          <textarea
            id="migration-payload"
            value={payloadText}
            onChange={(event) => { setPayloadText(event.target.value); setPreview(null) }}
            className="mt-2 min-h-[360px] w-full rounded-md border border-paper bg-background p-3 font-mono text-xs"
            spellCheck={false}
          />
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate(true)}
              className="rounded-md border border-midas-red px-4 py-2 text-sm text-midas-red disabled:opacity-50"
            >预演并校验</button>
            <button
              type="button"
              disabled={!canCommit || mutation.isPending}
              onClick={() => mutation.mutate(false)}
              className="rounded-md bg-midas-red px-4 py-2 text-sm text-white disabled:opacity-40"
            >确认导入本批</button>
          </div>
          {mutation.isError && <p className="mt-3 text-sm text-midas-red">校验或导入失败：{mutation.error.message}</p>}
          {preview && (
            <pre className="mt-3 overflow-auto rounded-md bg-background p-3 text-xs">
              {JSON.stringify(preview, null, 2)}
            </pre>
          )}
        </section>
      </main>
    </div>
  )
}
