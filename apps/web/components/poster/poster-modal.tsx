'use client'

/**
 * 邀请海报弹层(Phase 1.5 刀C)。
 *
 * 6 版风格切换(默认数据美学)+ 实时缩放预览 + 保存 PNG / 复制链接。
 * 海报在 1080×1920 真实坐标创作:预览靠祖先 transform 缩放,导出读未缩放根节点
 * (exportRef → 1080×1920 · 与预览比例无关)。移动端裂变场景:窄屏可用、拇指可达。
 */

import { Check, Copy, Download, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { PosterDark } from '@/components/poster/poster-dark'
import { PosterData } from '@/components/poster/poster-data'
import { exportPosterPng } from '@/components/poster/poster-export'
import { PosterInk } from '@/components/poster/poster-ink'
import { PosterInvite } from '@/components/poster/poster-invite'
import { PosterMinimal } from '@/components/poster/poster-minimal'
import { PosterTrend } from '@/components/poster/poster-trend'
import {
  POSTER_H,
  POSTER_VARIANTS,
  POSTER_W,
  type PosterProps,
  type PosterVariant,
} from '@/components/poster/types'

const RENDER: Record<PosterVariant, (p: PosterProps) => React.ReactNode> = {
  data: (p) => <PosterData {...p} />,
  invite: (p) => <PosterInvite {...p} />,
  ink: (p) => <PosterInk {...p} />,
  minimal: (p) => <PosterMinimal {...p} />,
  dark: (p) => <PosterDark {...p} />,
  trend: (p) => <PosterTrend {...p} />,
}

interface PosterModalProps {
  open: boolean
  onClose: () => void
  inviter: string
  code: string
  qrUrl: string
}

export function PosterModal({ open, onClose, inviter, code, qrUrl }: PosterModalProps) {
  const [variant, setVariant] = useState<PosterVariant>('data') // 默认数据美学(主版)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [scale, setScale] = useState(0.3)
  const exportRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)

  // 预览缩放:适配容器宽 + 视口高(留按钮/切换条空间)
  useEffect(() => {
    if (!open) return
    const fit = () => {
      const availW = stageRef.current?.clientWidth ?? 320
      const availH = window.innerHeight * 0.56
      setScale(Math.min(availW / POSTER_W, availH / POSTER_H))
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [open])

  // Esc 关闭 + 锁滚动
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null

  const props: PosterProps = { inviter, code, qrUrl }

  async function onSave() {
    if (!exportRef.current || busy) return
    setBusy(true)
    try {
      await exportPosterPng(exportRef.current, `midas-invite-${variant}-${code}.png`)
      toast.success('海报已保存')
    } catch (e) {
      toast.error('保存失败,请重试')
      console.error('[poster] export failed:', e)
    } finally {
      setBusy(false)
    }
  }

  async function onCopyLink() {
    try {
      await navigator.clipboard.writeText(qrUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      toast.error('复制失败,请手动复制')
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/55 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="邀请海报"
    >
      {/* 顶栏:标题 + 关闭 */}
      <div className="flex shrink-0 items-center justify-between px-5 py-3 text-white" onClick={(e) => e.stopPropagation()}>
        <span className="font-serif text-base font-bold">邀请海报</span>
        <button type="button" aria-label="关闭" onClick={onClose} className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-white/15">
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* 预览舞台 */}
      <div ref={stageRef} className="flex min-h-0 flex-1 items-center justify-center px-5" onClick={(e) => e.stopPropagation()}>
        <div
          style={{ width: POSTER_W * scale, height: POSTER_H * scale, overflow: 'hidden', boxShadow: '0 20px 60px rgba(0,0,0,.5)' }}
        >
          <div style={{ width: POSTER_W, height: POSTER_H, transform: `scale(${scale})`, transformOrigin: 'top left' }}>
            {/* exportRef → 未缩放 1080×1920 根(导出与预览比例无关) */}
            <div ref={exportRef}>{RENDER[variant](props)}</div>
          </div>
        </div>
      </div>

      {/* 底部控制条:风格切换 + 两操作(拇指可达) */}
      <div className="shrink-0 bg-background px-4 pb-[max(env(safe-area-inset-bottom),16px)] pt-3" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
          {POSTER_VARIANTS.map((v) => (
            <button
              key={v.key}
              type="button"
              onClick={() => setVariant(v.key)}
              className={
                v.key === variant
                  ? 'min-h-10 shrink-0 whitespace-nowrap rounded-full bg-midas-red px-4 text-sm font-medium text-white'
                  : 'min-h-10 shrink-0 whitespace-nowrap rounded-full border border-paper px-4 text-sm text-muted-foreground transition-colors hover:text-foreground'
              }
            >
              {v.label}
            </button>
          ))}
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onSave}
            disabled={busy}
            className="flex min-h-11 flex-1 items-center justify-center gap-2 rounded-md bg-midas-red text-sm font-medium text-white transition-colors hover:bg-midas-red/90 disabled:opacity-60"
          >
            <Download className="h-4 w-4" />
            {busy ? '生成中…' : '保存到相册'}
          </button>
          <button
            type="button"
            onClick={onCopyLink}
            className="flex min-h-11 flex-1 items-center justify-center gap-2 rounded-md border border-paper text-sm text-foreground transition-colors hover:border-midas-red"
          >
            {copied ? <Check className="h-4 w-4 text-midas-red" /> : <Copy className="h-4 w-4" />}
            {copied ? '已复制' : '复制邀请链接'}
          </button>
        </div>
      </div>
    </div>
  )
}
