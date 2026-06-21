/**
 * 官网区块 · Telegram 机器人 + 邮件订阅周报(支持的推送方式)。
 *
 * 版式照 components/landing/research-lab.tsx:section max-w-6xl + lg:grid-cols-2(文左·图右)+
 * 同款 eyebrow(text-gold tracking)/ 衬线标题 / 正文 token。
 * ★文案为产品负责人逐字定稿:① "交易下单"(2026-06 产品负责人改定 · 原"模拟下单")· ②"看 K 线图(Telegram)"
 *   保留标注 · ③ 其余功能条不做两端区分 · ④ 本区块不放任何底部声明小字。
 * ★2026-06-21 产品负责人决策(本次):**landing 此区块移除飞书展示**(机器人介绍只留 Telegram)·
 *   飞书后端代码 / 端点 / 字段全保留不删(仅前端/官网层去展示;设置页飞书改管理员可见)·
 *   未来 session 看到这里无飞书 = 有意为之,勿当回归加回。同区块新增「邮件订阅周报」亮点(A方案:
 *   纯展示文案,真正订阅在登录后设置页,本区块不放输入框 / 功能组件)。
 * 配图:public/marketing/bot-remote.png(Design 直供透明底免扣手机图 · 1380×1980 · RGBA)。
 */

import { Mail, Smartphone } from 'lucide-react'
import Image from 'next/image'

// 6 条功能(emoji + 逐字文案 · 顺序固定 · 均为 Telegram 机器人能力)
const FEATURES = [
  { icon: '📊', text: '查行情:四市场(加密 / 美股 / A股 / 港股),字母代码、数字代码、中文名都能认' },
  { icon: '📈', text: '看 K 线图(Telegram)' },
  { icon: '💼', text: '查自选、查持仓(现货 + 永续)' },
  { icon: '⚡', text: '交易下单:支持二次确认' },
  { icon: '🔔', text: '实时推送:成交、价格异动(±5%)、告警触发、强平提醒' },
  { icon: '🔕', text: '告警规则启停、安静时段设置' },
]

export function BotRemote() {
  return (
    <section id="bot" className="mx-auto max-w-6xl px-6 py-20">
      <div className="grid items-center gap-10 lg:grid-cols-2">
        {/* 左 · 文案 */}
        <div>
          <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-gold">
            <Smartphone className="h-4 w-4" />
            点金 MIDAS · 远程控制
          </p>
          <h2 className="font-serif text-3xl font-bold leading-snug lg:text-4xl">
            Telegram 机器人 · 把交易装进你的聊天软件
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground lg:text-base">
            绑定后,在 Telegram 里就能远程查行情、看持仓、下单,并实时收到成交与预警推送——不用一直盯着网页。
          </p>
          <ul className="mt-5 space-y-2.5 text-sm text-muted-foreground lg:text-base">
            {FEATURES.map((f) => (
              <li key={f.text} className="flex items-start gap-2.5">
                <span className="shrink-0 leading-relaxed" aria-hidden>
                  {f.icon}
                </span>
                <span className="leading-relaxed">{f.text}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* 右 · 手机 mockup(纯图 · DOM 在后 → lg 双列时在右,与研究室区左右交错) */}
        <div className="flex justify-center lg:justify-end">
          <Image
            src="/marketing/bot-remote.png"
            alt="点金机器人:在聊天软件里查行情、收推送、确认交易下单"
            width={1380}
            height={1980}
            className="h-auto w-full max-w-[300px]"
            sizes="(max-width: 1024px) 70vw, 300px"
          />
        </div>
      </div>

      {/* 第二个推送亮点 · 邮件订阅周报(A方案:纯展示文案,订阅操作在登录后设置页,本区块不放输入框) */}
      <div className="mt-12 rounded-2xl border border-paper bg-cream px-6 py-7 sm:px-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-midas-red/10 text-midas-red"
            aria-hidden
          >
            <Mail className="h-6 w-6" />
          </div>
          <div className="flex-1">
            <p className="mb-1 text-xs uppercase tracking-[0.3em] text-gold">
              另一种触达 · 无需机器人
            </p>
            <h3 className="font-serif text-lg font-bold leading-snug text-foreground lg:text-xl">
              邮件订阅 · 全球市场与行业机会周报
            </h3>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              每周一份精排周报(含 PDF)直达邮箱:行业强弱、核心结论、下周关注一览。登录后在「通知与提醒」设置页一键订阅。
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
