'use client'

/**
 * 「答题赢会员」官网首访弹窗 · B 期刀5(拉新推广训练营)· 刀5.1 接入 Claude Design 海报视觉。
 *
 * 触发:landing 首访 + 未登录 + 未看过(cookie)→ 短延迟弹一次。
 * 关闭(X / 点遮罩 / ESC,Radix Dialog 全内置)或点 CTA → 写 cookie,14 天不再弹。
 * ★纯前端展示 · 不碰后端/交易/支付/会员 · 响应式。
 * ★暗色策略 = 跟随项目 light-only(全站 .dark 永不挂载 · 见 globals.css 注释 + 训练营版块升级确认):
 *   弹窗也固定亮色,与全站一致、不割裂(刀5.3 从 5.1 的 prefers-color-scheme 暗色适配简化而来)。
 * ★合规:不含「稳赚 / 暴富 / 保证收益」· 带「教学内容不构成投资建议」。
 *
 * 视觉来源:Design 海报稿(红渐变头 + 徽章 + 衬线大标题 + 金条 + 三数字卡 + 三特性 + 红 CTA)·
 *   逻辑(cookie / CTA→/academy / 关闭)与上版一致,只换视觉。
 */

import * as DialogPrimitive from '@radix-ui/react-dialog'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { type ReactNode, useEffect, useState } from 'react'

import {
  Dialog,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from '@/components/ui/dialog'
import { hasSeenAcademyPromo, markAcademyPromoSeen } from '@/lib/academy-popup'
import { cn } from '@/lib/utils'

const GOLD_DEEP = '#B8860B'
const GOLD_BRIGHT = '#E8C14A'

// 设计稿 light 配色(★项目 light-only · 弹窗固定亮色 · 不随 OS 暗色翻转)
const CARD_BG = '#FFFFFF'
const STAT_BG = '#FBF6EA'
const STAT_BORDER = 'rgba(184,134,11,0.2)'
const ICON_BG = '#FBE9EC'
const SUB_TEXT = 'rgba(34,30,26,0.6)' // 数字卡标签 / 暂不按钮
const BODY_TEXT = 'rgba(34,30,26,0.82)' // 特性正文
const FINE_TEXT = 'rgba(34,30,26,0.42)' // 免责小字

const STATS = [
  { num: '6', label: '大模块课程' },
  { num: '217', label: '道练习题' },
  { num: '0', label: '真金风险' },
] as const

const FEATURES: { path: ReactNode; text: string }[] = [
  {
    path: (
      <>
        <path d="M3 17l5-5 4 3 8-9" stroke="#C8102E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M16 6h5v5" stroke="#C8102E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </>
    ),
    text: '从 K 线到缠论、合约、交易体系,系统学习',
  },
  {
    path: <path d="M5 13l4 4L19 7" stroke="#C8102E" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />,
    text: '通过模块结业测验,即可领取会员奖励',
  },
  {
    path: (
      <path
        d="M12 3l7 3v6c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6l7-3z"
        stroke="#C8102E"
        strokeWidth="1.9"
        strokeLinejoin="round"
      />
    ),
    text: '全程虚拟交易练习,零真金风险',
  },
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
      <DialogPortal>
        <DialogOverlay className="bg-black/60" />
        <DialogPrimitive.Content
          aria-describedby="promo-sub"
          className={cn(
            // ★照搬 shared DialogContent 的定位+动画类串(proven 居中):slide-in-from-*
            //   设 enter-translate=-50%/-48%,与静态 translate-[-50%] 配套,动画期/后都居中不偏。
            'fixed left-[50%] top-[50%] z-50 w-[380px] max-w-[calc(100vw-32px)]',
            'translate-x-[-50%] translate-y-[-50%] overflow-hidden rounded-[22px] shadow-2xl',
            'duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
            'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
            'data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%]',
            'data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]',
          )}
          style={{ background: CARD_BG }}
        >
          {/* 关闭(白圈 X · Radix Close → onOpenChange 写 cookie)*/}
          <DialogPrimitive.Close
            aria-label="关闭"
            className="absolute right-4 top-4 z-10 flex h-[30px] w-[30px] items-center justify-center rounded-full bg-white/16 backdrop-blur transition-colors hover:bg-white/25"
          >
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <path d="M1 1l11 11M12 1L1 12" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </DialogPrimitive.Close>

          {/* 红渐变头 */}
          <div
            className="relative overflow-hidden px-7 pb-7 pt-[30px]"
            style={{ background: 'linear-gradient(157deg,#E01430 0%,#C8102E 52%,#9C0C24 100%)' }}
          >
            <span className="pointer-events-none absolute -right-[50px] -top-[60px] h-[180px] w-[180px] rounded-full bg-white/[0.07]" />
            <span className="pointer-events-none absolute -bottom-[70px] -left-10 h-[150px] w-[150px] rounded-full bg-black/[0.08]" />

            {/* 徽章 */}
            <div className="relative inline-flex items-center gap-1.5 rounded-full border border-white/30 bg-white/15 px-3 py-1.5">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: GOLD_BRIGHT, boxShadow: `0 0 7px ${GOLD_BRIGHT}` }}
              />
              <span className="text-xs font-bold tracking-wide text-white">限时免费 · 答题赢会员</span>
            </div>

            <DialogTitle className="relative mt-[18px] font-serif text-[30px] font-black leading-[1.18] tracking-tight text-white sm:text-[33px]">
              学交易 · 赢会员
            </DialogTitle>
            <DialogDescription id="promo-sub" className="relative mt-3 text-[13.5px] leading-relaxed text-white/90">
              学完模块 + 通过结业测验,免费领会员
            </DialogDescription>
          </div>

          {/* 金色分隔条 */}
          <div
            className="h-1"
            style={{ background: `linear-gradient(90deg,${GOLD_DEEP},${GOLD_BRIGHT},${GOLD_DEEP})` }}
          />

          {/* 正文 */}
          <div className="px-7 pb-7 pt-6">
            {/* 三数字卡 */}
            <div className="grid grid-cols-3 gap-2.5">
              {STATS.map((s) => (
                <div
                  key={s.label}
                  className="rounded-[13px] border px-1.5 py-3.5 text-center"
                  style={{ background: STAT_BG, borderColor: STAT_BORDER }}
                >
                  <div className="font-serif text-[26px] font-black leading-none" style={{ color: GOLD_DEEP }}>
                    {s.num}
                  </div>
                  <div className="mt-1.5 text-[11.5px] font-medium leading-snug" style={{ color: SUB_TEXT }}>
                    {s.label}
                  </div>
                </div>
              ))}
            </div>

            {/* 三特性 */}
            <div className="mt-5 flex flex-col gap-3.5">
              {FEATURES.map((f, i) => (
                <div key={i} className="flex items-start gap-3">
                  <span
                    className="mt-px flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px]"
                    style={{ background: ICON_BG }}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
                      {f.path}
                    </svg>
                  </span>
                  <div className="pt-1 text-[13.5px] leading-normal" style={{ color: BODY_TEXT }}>
                    {f.text}
                  </div>
                </div>
              ))}
            </div>

            {/* 红 CTA → /academy(逻辑不变)*/}
            <button
              type="button"
              onClick={goAcademy}
              className="mt-6 flex h-[52px] w-full items-center justify-center gap-2.5 rounded-[13px] text-white transition-opacity hover:opacity-95"
              style={{
                background: 'linear-gradient(135deg,#E01430,#C8102E)',
                boxShadow: '0 10px 24px rgba(200,16,46,.34)',
              }}
            >
              <span className="text-base font-bold tracking-wide">免费开始学习</span>
              <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
                <path d="M3 8.5h10M9 4l4.2 4.5L9 13" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>

            <button
              type="button"
              onClick={close}
              className="mt-2 w-full rounded-lg py-2 text-sm transition-colors hover:opacity-80"
              style={{ color: SUB_TEXT }}
            >
              暂不,先逛逛
            </button>

            <p className="mt-3 text-center text-[11px] leading-relaxed" style={{ color: FINE_TEXT }}>
              训练营提供系统化交易知识与互动练习。
            </p>
          </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  )
}
