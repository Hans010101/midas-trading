'use client'

/**
 * 支付工单弹层(support 模块 · 技术故障客服通道)· 联系邮箱 + 类型 + 描述 + 图片(1-3 张 · 预览 + 预校验)。
 *
 * 🔴 前端只提交;图片随 multipart 上传,后端走 Resend 邮件附件【不落盘】。
 * 图片数量/类型/大小前端预校验(减少无效提交),与后端校验一致(3 张 · JPEG/PNG · ≤5MB)。
 */

import { Check, ImagePlus, Loader2, X } from 'lucide-react'
import { useSession } from 'next-auth/react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { useSubmitTicket } from '@/hooks/use-support'
import { SupportApiError, type TicketCategory } from '@/lib/api/support'
import { cn } from '@/lib/utils'

const MAX_IMAGES = 3
const MAX_MB = 5
const MAX_DESC = 2000
const ACCEPT = ['image/jpeg', 'image/png']
const CATEGORIES: { value: TicketCategory; label: string }[] = [
  { value: 'not_received', label: '未到账' },
  { value: 'duplicate_charge', label: '重复扣款' },
  { value: 'activation_failed', label: '开通失败' },
  { value: 'other', label: '其他问题' },
]

export function SupportTicketDialog({ onClose }: { onClose: () => void }) {
  const { data: session } = useSession()
  const submit = useSubmitTicket()

  const [category, setCategory] = useState<TicketCategory>('not_received')
  const [description, setDescription] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [emailEdited, setEmailEdited] = useState(false)
  const [images, setImages] = useState<File[]>([])

  const done = submit.isSuccess

  // 联系邮箱默认填充账号邮箱(用户未手动改时)
  useEffect(() => {
    if (!emailEdited && session?.user?.email) setContactEmail(session.user.email)
  }, [session, emailEdited])

  // 图片预览(对象 URL · 卸载/变更时回收防内存泄漏)
  const previews = useMemo(
    () => images.map((f) => ({ name: f.name, url: URL.createObjectURL(f) })),
    [images],
  )
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews])

  function addFiles(list: FileList | null) {
    if (!list) return
    const next = [...images]
    for (const f of Array.from(list)) {
      if (next.length >= MAX_IMAGES) {
        toast.error(`最多上传 ${MAX_IMAGES} 张图片`)
        break
      }
      if (!ACCEPT.includes(f.type)) {
        toast.error('图片仅支持 JPEG / PNG')
        continue
      }
      if (f.size > MAX_MB * 1024 * 1024) {
        toast.error(`单张图片不得超过 ${MAX_MB}MB`)
        continue
      }
      next.push(f)
    }
    setImages(next)
  }

  function removeImage(i: number) {
    setImages((prev) => prev.filter((_, idx) => idx !== i))
  }

  function handleSubmit() {
    const desc = description.trim()
    if (!desc) {
      toast.error('请填写问题描述')
      return
    }
    if (desc.length > MAX_DESC) {
      toast.error(`问题描述过长(上限 ${MAX_DESC} 字)`)
      return
    }
    submit.mutate(
      { category, description: desc, contactEmail: contactEmail.trim() || undefined, images },
      {
        onError: (e) =>
          toast.error(e instanceof SupportApiError ? e.detail : '提交失败,请稍后重试'),
      },
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg border border-gold/60 bg-cream p-6 shadow-xl">
        <h3 className="mb-4 text-center font-serif text-xl font-bold text-foreground">
          {done ? '工单已提交' : '联系客服'}
        </h3>

        {done ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-up/15">
              <Check className="h-7 w-7 text-up" />
            </div>
            <p className="text-sm text-foreground">
              {submit.data?.message ?? '工单已提交,我们会通过邮件与你联系'}
            </p>
            <p className="font-mono text-[11px] text-muted-foreground/60">
              工单号 #{submit.data?.ticket_id}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* 联系邮箱 */}
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">联系邮箱</label>
              <input
                type="email"
                value={contactEmail}
                onChange={(e) => {
                  setEmailEdited(true)
                  setContactEmail(e.target.value)
                }}
                placeholder="we@reply.to"
                className="w-full rounded-md border border-paper bg-background px-3 py-2 text-sm focus:border-gold focus:outline-none"
              />
            </div>

            {/* 类型 */}
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">问题类型</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as TicketCategory)}
                className="w-full rounded-md border border-paper bg-background px-3 py-2 text-sm focus:border-gold focus:outline-none"
              >
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>

            {/* 描述 */}
            <div>
              <label className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                <span>问题描述</span>
                <span className={cn(description.length > MAX_DESC && 'text-midas-red')}>
                  {description.length}/{MAX_DESC}
                </span>
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                placeholder="请描述你遇到的问题(如订单号、付款时间、付了多少、链上交易哈希等),便于我们核查。"
                className="w-full resize-none rounded-md border border-paper bg-background px-3 py-2 text-sm focus:border-gold focus:outline-none"
              />
            </div>

            {/* 图片(可选) */}
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">
                截图(可选 · 最多 {MAX_IMAGES} 张 · JPEG/PNG · ≤{MAX_MB}MB)
              </label>
              <div className="flex flex-wrap gap-2">
                {previews.map((p, i) => (
                  <div key={p.url} className="relative h-16 w-16 overflow-hidden rounded border border-paper">
                    {/* 本地预览图(对象 URL)· 非远端,next/image 不适用 */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={p.url} alt={p.name} className="h-full w-full object-cover" />
                    <button
                      type="button"
                      onClick={() => removeImage(i)}
                      aria-label="移除图片"
                      className="absolute right-0 top-0 flex h-4 w-4 items-center justify-center bg-foreground/60 text-white"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
                {images.length < MAX_IMAGES && (
                  <label className="flex h-16 w-16 cursor-pointer items-center justify-center rounded border border-dashed border-paper text-muted-foreground hover:border-gold hover:text-gold">
                    <ImagePlus className="h-5 w-5" />
                    <input
                      type="file"
                      accept={ACCEPT.join(',')}
                      multiple
                      className="hidden"
                      onChange={(e) => {
                        addFiles(e.target.files)
                        e.target.value = '' // 允许重复选同一文件
                      }}
                    />
                  </label>
                )}
              </div>
            </div>

            <button
              type="button"
              onClick={handleSubmit}
              disabled={submit.isPending}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-midas-red py-2.5 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:opacity-60"
            >
              {submit.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              提交工单
            </button>
            <p className="text-center text-[11px] leading-relaxed text-muted-foreground/70">
              我们预计会在 0-3 天内给您回复解决
            </p>
          </div>
        )}

        <button
          type="button"
          onClick={onClose}
          className={cn(
            'mt-5 w-full rounded-md py-2.5 text-sm font-medium transition-colors',
            done
              ? 'bg-midas-red text-white hover:bg-midas-red-deep'
              : 'border border-paper bg-background text-foreground hover:bg-cream',
          )}
        >
          {done ? '完成' : '关闭'}
        </button>
      </div>
    </div>
  )
}
