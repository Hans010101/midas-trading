'use client'

/**
 * 「答题赢会员」官网首访弹窗 · B 期刀5(拉新推广训练营)。
 *
 * 触发:landing 首访 + 未登录 + 未看过(cookie)→ 短延迟弹一次。
 * 关闭(X / 点遮罩 / ESC,Radix Dialog 全内置)或点 CTA → 写 cookie,14 天不再弹。
 * ★纯前端展示 · 不碰后端/交易/支付/会员 · 设计 token + 暗色自适应 · 响应式。
 * ★合规:不含「稳赚 / 暴富 / 保证收益」· 带「教学内容不构成投资建议」。
 *
 * 海报视觉:当前为文案+图标版(on-brand 中国红/帝王金)· Hans 给海报图后,
 *   把 <PosterArt/> 换成 next/image 即可(其余逻辑不动)。
 */

import { Award, BookOpen, GraduationCap, ListChecks, Sparkles } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { useEffect, useState } from 'react'

import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { hasSeenAcademyPromo, markAcademyPromoSeen } from '@/lib/academy-popup'

const HIGHLIGHTS = [
  { icon: BookOpen, text: '六大模块系统课 · 从 K 线到交易体系' },
  { icon: ListChecks, text: '随堂小测即时巩固 · 选项随机不死记' },
  { icon: GraduationCap, text: '模块结业测验 · 后端判分防作弊' },
  { icon: Award, text: '每过一个模块送 1 周会员 · 最多 6 周' },
]

export function AcademyPromoPopup() {
  const { status } = useSession()
  const router = useRouter()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (status === 'loading') return // 登录态未定 · 先不决定
    if (status === 'authenticated') return // 已登录用户不打扰
    if (hasSeenAcademyPromo()) return // 看过(14 天内)不再弹
    const t = setTimeout(() => setOpen(true), 1500) // 短延迟 · 让首屏先画出
    return () => clearTimeout(t)
  }, [status])

  function close() {
    markAcademyPromoSeen()
    setOpen(false)
  }

  function goAcademy() {
    markAcademyPromoSeen()
    setOpen(false)
    router.push('/academy')
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) close() // X / 遮罩 / ESC 关闭都写 cookie
      }}
    >
      <DialogContent className="max-w-md overflow-hidden border-gold/40 bg-cream p-0">
        {/* 海报头(中国红→帝王金渐变 · Hans 给海报图后换 next/image)*/}
        <PosterArt />

        <div className="px-6 pb-6 pt-4">
          <DialogTitle className="text-center font-serif text-xl font-bold text-foreground">
            学交易,赢会员
          </DialogTitle>
          <p className="mt-2 text-center text-sm leading-relaxed text-muted-foreground">
            免费学完一个模块、通过结业测验,就送 <span className="font-medium text-gold">1 周会员</span>
            ;六大模块全部通关,最多可赢 <span className="font-medium text-gold">6 周</span>。
          </p>

          <ul className="mt-4 space-y-2">
            {HIGHLIGHTS.map((h) => (
              <li key={h.text} className="flex items-center gap-2.5 text-sm text-foreground/85">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-midas-red/10 text-midas-red">
                  <h.icon className="h-4 w-4" />
                </span>
                {h.text}
              </li>
            ))}
          </ul>

          <div className="mt-6 flex flex-col gap-2">
            <button
              type="button"
              onClick={goAcademy}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-midas-red px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
            >
              <Sparkles className="h-4 w-4" />
              免费开始学习
            </button>
            <button
              type="button"
              onClick={close}
              className="rounded-lg px-5 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              暂不,先逛逛
            </button>
          </div>

          <p className="mt-4 text-center text-[11px] leading-relaxed text-muted-foreground/60">
            训练营为教学内容,仅供学习参考,不构成投资建议。
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** 海报头部视觉(占位版 · Hans 给海报图后替换为 next/image)。 */
function PosterArt() {
  return (
    <div className="relative flex h-32 items-center justify-center bg-gradient-to-br from-midas-red to-gold">
      <div className="text-center text-white">
        <GraduationCap className="mx-auto h-10 w-10" />
        <p className="mt-1 font-serif text-lg font-bold tracking-wide">答题赢会员</p>
      </div>
    </div>
  )
}
