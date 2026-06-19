/**
 * 官网区块 · Telegram / 飞书机器人(把点金装进聊天软件)。
 *
 * 版式照 components/landing/research-lab.tsx:section max-w-6xl + lg:grid-cols-2(文左·图右)+
 * 同款 eyebrow(text-gold tracking)/ 衬线标题 / 正文 token。
 * ★文案为产品负责人逐字定稿,不可改:① "模拟下单" 四字(非"下单"/"虚拟下单")· ②"看 K 线图(Telegram)"
 *   保留 (Telegram) 标注(飞书端无 K 线图,写上即失真)· ③ 其余 5 条 TG/飞书通用不做两端区分 ·
 *   ④ 本区块不放任何底部声明小字。
 * 配图:public/marketing/bot-remote.png(纯手机 mockup · 从 Design 合成稿裁出右侧手机 · 878×1292)。
 */

import { Smartphone } from 'lucide-react'
import Image from 'next/image'

// 6 条功能(emoji + 逐字文案 · 顺序固定)
const FEATURES = [
  { icon: '📊', text: '查行情:四市场(加密 / 美股 / A股 / 港股),字母代码、数字代码、中文名都能认' },
  { icon: '📈', text: '看 K 线图(Telegram)' },
  { icon: '💼', text: '查自选、查持仓(现货 + 永续)' },
  { icon: '⚡', text: '模拟下单:支持二次确认' },
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
            Telegram / 飞书机器人 · 把点金装进你的聊天软件
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground lg:text-base">
            绑定后,在 Telegram 或飞书里就能远程查行情、看持仓、下单,并实时收到成交与预警推送——不用一直盯着网页。
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
            alt="点金机器人:在聊天软件里查行情、收推送、确认模拟下单"
            width={878}
            height={1292}
            className="h-auto w-full max-w-[300px]"
            sizes="(max-width: 1024px) 70vw, 300px"
          />
        </div>
      </div>
    </section>
  )
}
