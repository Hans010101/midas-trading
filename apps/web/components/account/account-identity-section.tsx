'use client'

/**
 * 账户身份区(个人中心)· 头像(+ 预设选择器)+ 邮箱/用户ID + 修改密码。
 *
 * 交互:更换头像 / 修改密码 两按钮并排,下方【互斥展开】单一面板(单一 panel 状态保证不重叠)。
 * 选头像 = 选中即保存 + 自动收起;改密码保存成功亦收起。
 *
 * 🔴 红线:头像零图片存储(只选预设编号 · 不上传)· 密码明文不持久化 ·
 * OAuth-only 用户(has_password=false)不显示改密码按钮(显示 Google 提示)。
 */

import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { UserAvatar } from '@/components/account/user-avatar'
import { useChangePassword, useMe, useSetAvatar } from '@/hooks/use-me'
import { MeApiError } from '@/lib/api/me'
import { AVATAR_IDS, isPresetAvatar } from '@/lib/avatars'
import { cn } from '@/lib/utils'

const MIN_PW = 8

type Panel = 'avatar' | 'password' | null

export function AccountIdentitySection() {
  const { data: me } = useMe()
  // 单一状态保证两面板互斥(同时只开一个)
  const [panel, setPanel] = useState<Panel>(null)
  const toggle = (p: Exclude<Panel, null>) => setPanel((cur) => (cur === p ? null : p))

  const btnCls = (active: boolean) =>
    cn(
      'rounded-md border px-3 py-1.5 text-xs transition-colors',
      active
        ? 'border-gold bg-gold/10 text-gold'
        : 'border-paper text-muted-foreground hover:border-gold hover:text-gold',
    )

  return (
    <section className="mb-10">
      <h2 className="mb-3 font-serif text-xl font-bold text-foreground">账户基本信息</h2>
      <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
        {/* 头像 + 邮箱/ID + 操作按钮(同排最右:更换头像 / 修改密码)· OAuth 无密码不出改密码按钮 */}
        <div className="flex items-center gap-4">
          <UserAvatar email={me?.email} avatarId={me?.avatar_id} size={56} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-sm text-foreground">{me?.email ?? '—'}</p>
            <p className="truncate font-mono text-[11px] text-muted-foreground/70">
              ID {me?.user_id ?? '—'}
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <button type="button" onClick={() => toggle('avatar')} className={btnCls(panel === 'avatar')}>
              更换头像
            </button>
            {me?.has_password && (
              <button
                type="button"
                onClick={() => toggle('password')}
                className={btnCls(panel === 'password')}
              >
                修改密码
              </button>
            )}
          </div>
        </div>

        {/* OAuth-only 提示(无密码用户)*/}
        {me && !me.has_password && (
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
            你通过 Google 登录,账户安全由 Google 管理(无需在此设置密码)。
          </p>
        )}

        {/* 互斥展开面板(同时只渲染一个)*/}
        {panel === 'avatar' && (
          <AvatarPicker
            email={me?.email}
            current={me?.avatar_id ?? null}
            onSaved={() => setPanel(null)}
          />
        )}
        {panel === 'password' && (
          <div className="mt-4 border-t border-paper pt-4">
            <ChangePasswordForm onDone={() => setPanel(null)} />
          </div>
        )}
      </div>
    </section>
  )
}

// ── 头像选择器(默认首字母单独一行 + 16 预设 8×2 网格)· 选中即存 + 自动收起 ──────

function AvatarPicker({
  email,
  current,
  onSaved,
}: {
  email?: string | null
  current: number | null
  onSaved: () => void
}) {
  const setAvatar = useSetAvatar()

  function choose(id: number) {
    if (setAvatar.isPending) return
    setAvatar.mutate(id, {
      onSuccess: () => {
        toast.success('头像已更新')
        onSaved() // 选中 = 确认 + 收起
      },
      onError: () => toast.error('头像更新失败,请重试'),
    })
  }

  const cellCls = (selected: boolean) =>
    cn(
      'rounded-full ring-offset-2 ring-offset-background transition-shadow',
      selected ? 'ring-2 ring-midas-red' : 'hover:ring-2 hover:ring-gold/50',
    )

  return (
    <div className="mt-4 rounded-md border border-paper bg-background p-3">
      <p className="mb-2 text-[11px] text-muted-foreground/70">选择头像</p>

      {/* 默认(邮箱首字母)· 单独一行 */}
      <button
        type="button"
        onClick={() => choose(0)}
        aria-label="默认头像(首字母)"
        className={cn(
          'mb-3 inline-flex items-center gap-2 rounded-full pr-3',
          !isPresetAvatar(current) && 'ring-2 ring-midas-red ring-offset-2 ring-offset-background',
        )}
      >
        <UserAvatar email={email} avatarId={null} size={40} />
        <span className="text-xs text-muted-foreground">默认 · 邮箱首字母</span>
      </button>

      {/* 16 预设 · 窄屏 4 列 / sm+ 8 列(8×2 对齐)*/}
      <div className="grid grid-cols-4 justify-items-center gap-3 sm:grid-cols-8">
        {AVATAR_IDS.map((id) => (
          <button
            type="button"
            key={id}
            onClick={() => choose(id)}
            aria-label={`头像 ${id}`}
            className={cellCls(current === id)}
          >
            <UserAvatar avatarId={id} size={40} />
          </button>
        ))}
      </div>
    </div>
  )
}

// ── 修改密码表单(旧 + 新 + 确认 · 前端先校验)──────────────────────────────────

function ChangePasswordForm({ onDone }: { onDone: () => void }) {
  const change = useChangePassword()
  const [oldPw, setOldPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirm, setConfirm] = useState('')

  function submit() {
    if (!oldPw) {
      toast.error('请输入当前密码')
      return
    }
    if (newPw.length < MIN_PW) {
      toast.error(`新密码至少 ${MIN_PW} 位`)
      return
    }
    if (newPw !== confirm) {
      toast.error('两次输入的新密码不一致')
      return
    }
    change.mutate(
      { oldPassword: oldPw, newPassword: newPw },
      {
        onSuccess: () => {
          toast.success('密码已修改')
          onDone()
        },
        onError: (e) =>
          toast.error(e instanceof MeApiError ? e.detail : '修改失败,请稍后重试'),
      },
    )
  }

  const inputCls =
    'w-full rounded-md border border-paper bg-background px-3 py-2 text-sm focus:border-gold focus:outline-none'

  return (
    <div className="space-y-2">
      <input
        type="password"
        value={oldPw}
        onChange={(e) => setOldPw(e.target.value)}
        placeholder="当前密码"
        autoComplete="current-password"
        className={inputCls}
      />
      <input
        type="password"
        value={newPw}
        onChange={(e) => setNewPw(e.target.value)}
        placeholder={`新密码(至少 ${MIN_PW} 位)`}
        autoComplete="new-password"
        className={inputCls}
      />
      <input
        type="password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        placeholder="确认新密码"
        autoComplete="new-password"
        className={inputCls}
      />
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={submit}
          disabled={change.isPending}
          className="inline-flex items-center gap-1.5 rounded-md bg-midas-red px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-midas-red-deep disabled:opacity-60"
        >
          {change.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          保存
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-md border border-paper px-4 py-1.5 text-xs text-muted-foreground hover:bg-cream"
        >
          取消
        </button>
      </div>
    </div>
  )
}
