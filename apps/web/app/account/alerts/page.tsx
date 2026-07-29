'use client'

/**
 * 通知与提醒(用户中心模块③ · 重组刀2 实装)。
 *
 * 从 /settings 搬入(P2 已证两 section 零 props 自包含 · 组件内部零改动):
 *   ① 消息推送配置(TG/飞书绑定 + 事件开关 + 免打扰)
 *   ② 价格预警规则(CRUD + 一键推荐)
 */

import { AlertRulesSection } from '@/components/settings/alert-rules-section'
import { NotificationsConfigSection } from '@/components/settings/notifications-config-section'
import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'

export default function AlertsPage() {
  const { locale } = useRuntimeLocale()
  return (
    <div>
      <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">
        {locale === 'en' ? 'Alerts & notifications' : '通知与提醒'}
      </h1>
      <NotificationsConfigSection />
      <AlertRulesSection />
    </div>
  )
}
