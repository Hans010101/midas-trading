'use client'

/**
 * 用户管理(刀2)· 管理员用户列表页 · /admin 独立域(不进 /account 个人中心)。
 *
 * ★ 安全边界在后端 AdminDep(403):本页所有数据来自 admin API,
 *   普通用户手输 URL → 后端 403 → 无权限降级提示(不渲染空表)。
 *   middleware 只兜「未登录跳登录」,页面不做任何"安全"判定。
 */

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import { AdminApiError, fetchAdminUsers } from '@/lib/api/admin'
import { createdAtText, lastActiveText, registerMethodLabel } from '@/lib/admin-view'

const PAGE_SIZE = 20

export default function AdminUsersPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const [page, setPage] = useState(1)

  const query = useQuery({
    queryKey: ['admin-users', page],
    queryFn: ({ signal }) => fetchAdminUsers(token, { page, pageSize: PAGE_SIZE }, signal),
    enabled: token !== '',
  })

  const forbidden = query.error instanceof AdminApiError && query.error.status === 403
  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <AdminNav />
        {query.data && (
          <p className="mb-4 text-sm text-muted-foreground">
            共 <span className="font-mono font-bold text-foreground">{query.data.total}</span> 位用户
          </p>
        )}

        {/* 后端 403(普通用户手输 URL)→ 无权限降级 · 不渲染空表 */}
        {forbidden ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center shadow-sm">
            <p className="text-sm text-muted-foreground">该页面仅管理员可见。</p>
            <Link
              href="/global"
              className="mt-3 inline-block rounded-md bg-midas-red px-4 py-1.5 text-sm text-white transition-colors hover:bg-midas-red/90"
            >
              返回首页
            </Link>
          </div>
        ) : query.status === 'error' ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center text-sm text-muted-foreground shadow-sm">
            加载失败,请稍后重试。
          </div>
        ) : (
          <>
            <div className="overflow-x-auto rounded-lg border border-paper bg-cream shadow-sm">
              <table className="w-full min-w-[820px] text-sm">
                <thead>
                  <tr className="border-b border-paper text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2.5 font-normal">邮箱</th>
                    <th className="px-4 py-2.5 font-normal">注册时间</th>
                    <th className="px-4 py-2.5 font-normal">验证</th>
                    <th className="px-4 py-2.5 font-normal">方案</th>
                    <th className="px-4 py-2.5 font-normal">注册方式</th>
                    <th className="px-4 py-2.5 font-normal">最后活跃(7d)</th>
                    <th className="px-4 py-2.5 text-right font-normal">设备</th>
                  </tr>
                </thead>
                <tbody>
                  {(query.data?.items ?? []).map((u) => (
                    <tr key={u.id} className="border-b border-paper/60 last:border-0">
                      <td className="px-4 py-2.5">
                        {/* 刀3a:邮箱可点 → 用户详情(纯只读聚合) */}
                        <Link
                          href={`/admin/users/${u.id}`}
                          className="font-mono text-xs text-foreground transition-colors hover:text-midas-red hover:underline"
                        >
                          {u.email}
                        </Link>
                        {u.role === 'admin' && (
                          <span className="ml-1.5 rounded bg-gold/15 px-1.5 py-0.5 text-[10px] text-gold">
                            admin
                          </span>
                        )}
                        {u.banned && (
                          <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            已停用
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                        {createdAtText(u.created_at)}
                      </td>
                      <td className="px-4 py-2.5 text-xs">
                        {u.email_verified ? (
                          <span className="text-up">已验证</span>
                        ) : (
                          <span className="text-muted-foreground/60">未验证</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        {u.plan === 'free' ? (
                          <span className="text-xs text-muted-foreground/60">free</span>
                        ) : (
                          <span className="rounded bg-gold/15 px-1.5 py-0.5 text-[11px] text-gold">
                            {u.plan}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="rounded bg-surface-subtle px-1.5 py-0.5 text-[11px] text-muted-foreground">
                          {registerMethodLabel(u.register_method)}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                        {lastActiveText(u.last_active_7d)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs">
                        {u.active_sessions}
                      </td>
                    </tr>
                  ))}
                  {query.status === 'pending' && (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-xs text-muted-foreground/60">
                        加载中…
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* 分页(created_at desc · 后端上限 page_size=100,本页固定 20) */}
            <div className="mt-3 flex items-center justify-end gap-2 text-xs">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="min-h-10 rounded border border-paper px-2.5 py-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 lg:min-h-0"
              >
                上一页
              </button>
              <span className="font-mono text-muted-foreground">
                {page} / {totalPages}
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="min-h-10 rounded border border-paper px-2.5 py-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 lg:min-h-0"
              >
                下一页
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
