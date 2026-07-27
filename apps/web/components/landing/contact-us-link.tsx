'use client'

/**
 * 页脚「联系我们」· 复用现有工单系统(不新建后端端点)。
 *
 * 登录用户 → 打开工单弹层(同个人中心提工单)· 未登录 → 提示并跳登录(工单需登录)。
 * 未登录访客先进入独立登录流程,避免把工单发送到旧项目邮箱。
 */

import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { toast } from 'sonner'

import { SupportTicketDialog } from '@/components/account/support-ticket-dialog'

export function ContactUsLink({ className }: { className?: string }) {
  const { data: session } = useSession()
  const router = useRouter()
  const [open, setOpen] = useState(false)

  function handleClick() {
    if (session?.accessToken) {
      setOpen(true)
    } else {
      toast('请先登录后通过站内客服通道提交工单')
      router.push('/login')
    }
  }

  return (
    <>
      <button type="button" onClick={handleClick} className={className}>
        联系我们
      </button>
      {open && <SupportTicketDialog onClose={() => setOpen(false)} />}
    </>
  )
}
