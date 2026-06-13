'use client'

/**
 * 用户详情(用户管理刀3a · 纯只读聚合)。
 *
 * 基础 / 会员(plan 金徽+到期日)/ 今日额度 / 邀请统计 / 兑换记录,分区只读展示。
 * 「管理员操作」区占位(刀3b 接调权益/封禁)。🔴 本页零写操作。
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useSession } from 'next-auth/react'

import { BanSection } from '@/components/admin/ban-section'
import { GrantProSection } from '@/components/admin/grant-pro-section'
import { TopNav } from '@/components/layout/top-nav'
import { AdminApiError, type AdminUserDetail, fetchAdminUserDetail } from '@/lib/api/admin'
import { createdAtText } from '@/lib/admin-view'
import { periodLabel } from '@/lib/redeem-view'

const ACTION_LABEL: Record<string, string> = { grant_pro: '授予 Pro' }

const PLAN_LABEL: Record<string, string> = { free: '免费版', pro: '进阶版 Pro' }
const SOURCE_LABEL: Record<string, string> = {
  trial: '试用', invite: '邀请', redeem: '兑换', paid: '付费', manual: '手动',
}

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

            <Card title="会员">
              <dl>
                <Row label="方案">
                  {d.plan === 'free' ? (
                    <span className="text-muted-foreground">免费版</span>
                  ) : (
                    <span className="font-bold text-gold">{PLAN_LABEL[d.plan] ?? d.plan}</span>
                  )}
                </Row>
                {d.plan_expires_at && (
                  <Row label="到期">{new Date(d.plan_expires_at).toLocaleDateString('zh-CN')}</Row>
                )}
                {d.plan_source && <Row label="来源">{SOURCE_LABEL[d.plan_source] ?? d.plan_source}</Row>}
                {d.plan_status && <Row label="状态">{d.plan_status}</Row>}
              </dl>
            </Card>

            <Card title="今日额度">
              <dl>
                {d.quota.map((q) => (
                  <Row key={q.feature} label={q.feature === 'diagnose' ? '沙盘诊断' : '回测'}>
                    <span className="font-mono">{q.used ?? '—'}/{q.limit}</span>
                  </Row>
                ))}
              </dl>
            </Card>

            <Card title="邀请">
              <dl>
                <Row label="邀请码">
                  <span className="font-mono">{d.invite_code ?? '— 未生成'}</span>
                </Row>
                <Row label="已邀请">{d.invited_count} 人</Row>
                <Row label="已兑现">{d.rewarded_count} 人</Row>
              </dl>
            </Card>

            <Card title={`兑换记录(${d.redeemed.length})`}>
              {d.redeemed.length === 0 ? (
                <p className="text-xs text-muted-foreground/60">无</p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {d.redeemed.map((rc) => (
                    <li key={rc.code} className="flex justify-between gap-4">
                      <span className="font-mono text-xs text-foreground">{rc.code}</span>
                      <span className="text-muted-foreground">
                        {periodLabel(rc.period)} · {new Date(rc.redeemed_at).toLocaleDateString('zh-CN')}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            {/* 管理员操作 · 调整权益(刀3b-1)· 封禁留 3b-2 */}
            <GrantProSection
              userId={d.id}
              email={d.email}
              token={token}
              onGranted={() => void qc.invalidateQueries({ queryKey: ['admin-user-detail', id] })}
            />

            {/* 封禁/解封(刀3b-2)*/}
            <BanSection
              userId={d.id}
              email={d.email}
              banned={d.banned}
              token={token}
              onChanged={() => void qc.invalidateQueries({ queryKey: ['admin-user-detail', id] })}
            />

            {/* 操作历史(刀3b:该用户被调权益记录)*/}
            {d.admin_actions.length > 0 && (
              <Card title={`操作历史(${d.admin_actions.length})`}>
                <ul className="space-y-1.5 text-sm">
                  {d.admin_actions.map((a, i) => (
                    <li key={i} className="flex justify-between gap-4">
                      <span className="text-foreground">
                        {ACTION_LABEL[a.action] ?? a.action}
                        {typeof a.detail.days === 'number' && (
                          <span className="ml-1.5 text-muted-foreground">+{a.detail.days} 天</span>
                        )}
                        {typeof a.detail.note === 'string' && a.detail.note && (
                          <span className="ml-1.5 text-xs text-muted-foreground/70">· {a.detail.note}</span>
                        )}
                      </span>
                      <span className="shrink-0 font-mono text-xs text-muted-foreground/70">
                        {new Date(a.created_at).toLocaleString('zh-CN')}
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
