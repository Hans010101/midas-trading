'use client'

/**
 * 邀请海报弹层(Phase 1.5 刀C)。
 *
 * 6 版风格切换(默认数据美学)+ 实时缩放预览 + 保存 PNG / 复制链接。
 * 海报在 1080×1920 真实坐标创作:预览靠祖先 transform 缩放,导出读未缩放根节点
 * (exportRef → 1080×1920 · 与预览比例无关)。移动端裂变场景:窄屏可用、拇指可达。
 */

import { Check, Copy, Download, Shuffle, X } from 'lucide-react'
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

// 「换个样式」循环顺序(Hans 拍 · 固定)· 默认渲染首个 invite。
// 与展示名解耦:用户不再看见风格词 tab,只按此序循环浏览。
const CYCLE: PosterVariant[] = ['invite', 'data', 'trend', 'ink', 'minimal', 'dark']

export function PosterModal({ open, onClose, inviter, code, qrUrl }: PosterModalProps) {
  const [variant, setVariant] = useState<PosterVariant>('invite') // 默认邀请函(循环首位)
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
  const cycleIdx = CYCLE.indexOf(variant)
  const cycleNext = () => setVariant(CYCLE[(cycleIdx + 1) % CYCLE.length])

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
            {/* exportRef → 未缩放 1080×1920 根(导出与预览比例无关)·
                key={variant} 切换时 remount → poster-fade 轻淡入(感知「换了一张」) */}
            <div key={variant} ref={exportRef} style={{ animation: 'poster-fade .28s ease' }}>
              {RENDER[variant](props)}
            </div>
          </div>
        </div>
      </div>

      {/* 底部控制条:三按钮并排一行(Hans 反馈 · 保存=主按钮红底突出)。
          ★ 375 放下三个:图标 + 窄屏短标签(保存/换样式/复制),sm 起显全
          (保存到相册/换个样式/复制邀请链接);各 flex-1 等分 + px 收紧 + nowrap。 */}
      <div className="shrink-0 bg-background px-4 pb-[max(env(safe-area-inset-bottom),16px)] pt-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex gap-2">
          {/* 保存 = 主按钮(红底 · 默认最突出) */}
          <button
            type="button"
            onClick={onSave}
            disabled={busy}
            className="flex min-h-11 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-md bg-midas-red px-2 text-sm font-medium text-white transition-colors hover:bg-midas-red/90 disabled:opacity-60"
          >
            <Download className="h-4 w-4 shrink-0" />
            {busy ? '生成中…' : (
              <>
                <span className="sm:hidden">保存</span>
                <span className="hidden sm:inline">保存到相册</span>
              </>
            )}
          </button>
          {/* 换个样式 = 次级(循环 · N/6 克制) */}
          <button
            type="button"
            onClick={cycleNext}
            className="flex min-h-11 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-paper px-2 text-sm font-medium text-foreground transition-colors hover:border-midas-red hover:text-midas-red"
          >
            <Shuffle className="h-4 w-4 shrink-0" />
            <span className="sm:hidden">换样式</span>
            <span className="hidden sm:inline">换个样式</span>
            <span className="font-mono text-xs text-muted-foreground/60">
              {cycleIdx + 1}/{CYCLE.length}
            </span>
          </button>
          {/* 复制 = 次级 */}
          <button
            type="button"
            onClick={onCopyLink}
            className="flex min-h-11 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-paper px-2 text-sm text-foreground transition-colors hover:border-midas-red"
          >
            {copied ? <Check className="h-4 w-4 shrink-0 text-midas-red" /> : <Copy className="h-4 w-4 shrink-0" />}
            {copied ? '已复制' : (
              <>
                <span className="sm:hidden">复制</span>
                <span className="hidden sm:inline">复制邀请链接</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
