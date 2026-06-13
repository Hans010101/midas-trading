'use client'

/**
 * 封禁/解封区(用户管理刀3b-2 · 写操作 · 方案A 禁止登录)。
 *
 * 封禁措辞重 + 二次确认("确认停用 {email}?该用户将立即无法登录")→ POST /ban → 刷新。
 * 已封禁显示解封(对称)。🔴 只调 ban/unban 端点(后端写 banned_at+审计+登录链检查)。
 */

import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import { setBan } from '@/lib/api/admin'

export function BanSection({
  userId,
  email,
  banned,
  token,
  onChanged,
}: {
  userId: string
  email: string
  banned: boolean
  token: string
  onChanged: () => void
}) {
  const [confirming, setConfirming] = useState(false)

  const mut = useMutation({
    mutationFn: () => setBan(token, userId, !banned),
    onSuccess: (res) => {
      toast.success(res.banned ? '已停用该账号' : '已恢复该账号')
      setConfirming(false)
      onChanged()
    },
    onError: () => {
      toast.error('操作失败,请重试')
      setConfirming(false)
    },
  })

  return (
    <section className="rounded-lg border border-paper bg-surface-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-serif text-base font-bold">账号状态</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {banned ? '已停用 · 该账号无法登录' : '正常 · 可登录'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={mut.isPending}
          className={
            banned
              ? 'min-h-10 shrink-0 rounded-md border border-down px-4 text-sm font-medium text-down transition-colors hover:bg-down/10 disabled:opacity-60'
              : 'min-h-10 shrink-0 rounded-md border border-midas-red px-4 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow disabled:opacity-60'
          }
        >
          {banned ? '恢复账号' : '停用账号'}
        </button>
      </div>

      {/* ★ 二次确认(封禁措辞重)*/}
      {confirming && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => !mut.isPending && setConfirming(false)}
        >
          <div
            className="w-full max-w-sm rounded-lg bg-background p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-2 font-serif text-base font-bold">
              {banned ? '确认恢复' : '确认停用'}
            </h3>
            <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
              {banned ? (
                <>
                  将恢复 <span className="font-mono text-foreground">{email}</span> 的账号,该用户可重新登录。
                </>
              ) : (
                <>
                  确认停用 <span className="font-mono text-foreground">{email}</span>?
                  <span className="text-midas-red">该用户将立即无法登录(现有会话同时失效)。</span>
                </>
              )}
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={mut.isPending}
                className="min-h-10 rounded-md border border-paper px-4 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => mut.mutate()}
                disabled={mut.isPending}
                className={
                  banned
                    ? 'min-h-10 rounded-md bg-down px-5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60'
                    : 'min-h-10 rounded-md bg-midas-red px-5 text-sm font-medium text-white transition-colors hover:bg-midas-red/90 disabled:opacity-60'
                }
              >
                {mut.isPending ? '处理中…' : banned ? '确认恢复' : '确认停用'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
