'use client'

/**
 * /settings · 系统设置(段 1 补丁 B 重组 · 段 2 Task 6 填充推送)。
 *
 * M0 内容:
 *  - 消息推送配置容器(段 2 填充飞书/TG 配置 UI)
 *  - 关键指标预警配置容器(段 2 填充)
 *  - 偏好 / 安全(M1 占位灰显)
 *
 * 跟 /account 区分:那里是「账户级数据 + 资金管理」,
 * 这里是「系统级配置」(改这些不影响交易数据)。
 */

import { TopNav } from '@/components/layout/top-nav'
import { NotificationsConfigSection } from '@/components/settings/notifications-config-section'

export default function SettingsPage() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-4xl px-6 py-8">
        <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">
          设置
        </h1>

        <NotificationsConfigSection />

        {/* M1 占位 */}
        <PlaceholderSection
          title="偏好设置"
          milestone="M1"
          description="主题切换 · 默认市场 · 默认数量 · 时区"
        />
        <PlaceholderSection
          title="安全设置"
          milestone="M1"
          description="密码修改 · 2FA · 登录设备管理 · 操作日志"
        />

        <p className="mt-12 text-center text-xs text-muted-foreground/70">
          模拟交易,不构成投资建议
        </p>
      </main>
    </div>
  )
}

interface PlaceholderProps {
  title: string
  milestone: string
  description: string
}

function PlaceholderSection({ title, milestone, description }: PlaceholderProps) {
  return (
    <section className="mb-6 rounded-lg border border-dashed border-paper bg-surface-card p-5">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="font-serif text-lg font-bold text-muted-foreground/70">
          {title}
        </h2>
        <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          {milestone} 待实装
        </span>
      </div>
      <p className="text-xs text-muted-foreground/70">{description}</p>
    </section>
  )
}
