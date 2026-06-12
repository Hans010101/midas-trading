'use client'

/**
 * /settings · 设置已迁移提示页(重组刀2)。
 *
 * 四个 section 已搬入用户中心四模块(不留双份防维护漂移):
 *   通知配置 + 价格预警 → /account/alerts;涨跌色 + Bot 预设 → /account/profile。
 * 本页留提示 + 链接过渡(bot 回执/旧书签仍指这里);整页 redirect 是重组刀4。
 */

import Link from 'next/link'

import { TopNav } from '@/components/layout/top-nav'

const MOVED: Array<{ label: string; href: string; hint: string }> = [
  { label: '通知与提醒', href: '/account/alerts', hint: 'TG/飞书绑定 · 事件开关 · 免打扰 · 价格预警' },
  { label: '账号与偏好', href: '/account/profile', hint: '账号信息 · 涨跌色 · Bot 下单预设 · 安全' },
  { label: '资产总览', href: '/account', hint: '虚拟资金管理 · KPI · 权益曲线' },
  { label: '持仓与订单', href: '/account/positions', hint: '持仓 · 订单流水 · 条件单' },
]

export default function SettingsPage() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-4xl px-6 py-8">
        <h1 className="mb-3 font-serif text-2xl font-bold text-foreground">设置已迁移</h1>
        <p className="mb-6 text-sm text-muted-foreground">
          设置项已并入「用户中心」四模块(头像菜单可直达):
        </p>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {MOVED.map((m) => (
            <Link
              key={m.href}
              href={m.href}
              className="rounded-lg border border-paper bg-cream p-4 shadow-sm transition-colors hover:border-midas-red/50"
            >
              <div className="mb-1 font-serif text-base font-bold text-midas-red">{m.label}</div>
              <div className="text-xs text-muted-foreground">{m.hint}</div>
            </Link>
          ))}
        </div>
      </main>
    </div>
  )
}
