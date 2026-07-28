'use client'

/**
 * 用户详情(用户管理刀3a · 纯只读聚合)。
 *
 * 基础 / 系统容量 / 安全与自动交易权限。
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useSession } from 'next-auth/react'

import { BanSection } from '@/components/admin/ban-section'
import { PlatinumSection } from '@/components/admin/platinum-section'
import { TopNav } from '@/components/layout/top-nav'
import { AdminApiError, type AdminUserDetail, fetchAdminUserDetail } from '@/lib/api/admin'
import { createdAtText } from '@/lib/admin-view'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right text-foreground">{children}</dd>
    </div>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
      <h2 className="mb-2 font-serif text-base font-bold">{title}</h2>
      {children}
    </section>
  )
}

export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>()
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const id = params.id
  const qc = useQueryClient()

  const query = useQuery({
    queryKey: ['admin-user-detail', id],
    queryFn: ({ signal }) => fetchAdminUserDetail(token, id, signal),
    enabled: token !== '' && !!id,
  })
  const err = query.error instanceof AdminApiError ? query.error : null
  const forbidden = err?.status === 403
  const notFound = err?.status === 404
  const d: AdminUserDetail | undefined = query.data

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-3xl px-6 py-8">
        <Link
          href="/admin"
          className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          返回用户列表
        </Link>

        {forbidden ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center text-sm text-muted-foreground shadow-sm">
            该页面仅管理员可见。
          </div>
        ) : notFound ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center text-sm text-muted-foreground shadow-sm">
            用户不存在。
          </div>
        ) : d === undefined ? (
          <p className="text-sm text-muted-foreground/60">
            {query.status === 'error' ? '加载失败,请重试' : '加载中…'}
          </p>
        ) : (
          <div className="space-y-5">
            <h1 className="flex items-center gap-2 font-mono text-lg font-bold text-foreground">
              {d.email}
              {d.banned && (
                <span className="rounded bg-muted px-1.5 py-0.5 font-sans text-[11px] text-muted-foreground">
                  已停用
                </span>
              )}
            </h1>

            <Card title="基础">
              <dl>
                <Row label="角色">{d.role}</Row>
                <Row label="注册时间">{createdAtText(d.created_at)}</Row>
                <Row label="邮箱验证">
                  {d.email_verified ? <span className="text-up">已验证</span> : <span className="text-muted-foreground/60">未验证</span>}
                </Row>
              </dl>
            </Card>

            <Card title="系统容量">
              <dl>
                {d.quota.map((q) => (
                  <Row key={q.feature} label={q.feature === 'diagnose' ? '沙盘诊断' : '回测'}>
                    <span className="font-mono">{q.used ?? '—'}/{q.limit}</span>
                  </Row>
                ))}
              </dl>
            </Card>

            {/* 封禁/解封(刀3b-2)*/}
            <BanSection
              userId={d.id}
              email={d.email}
              banned={d.banned}
              token={token}
              onChanged={() => void qc.invalidateQueries({ queryKey: ['admin-user-detail', id] })}
            />

            {/* ★铂金标记(多账户 PR-1 · superadmin 手动设 · 享受所有 pro 权益 + 托管/智能交易)*/}
            <PlatinumSection
              userId={d.id}
              email={d.email}
              isPlatinum={d.is_platinum}
              token={token}
              onChanged={() => void qc.invalidateQueries({ queryKey: ['admin-user-detail', id] })}
            />

          </div>
        )}
      </main>
    </div>
  )
}
