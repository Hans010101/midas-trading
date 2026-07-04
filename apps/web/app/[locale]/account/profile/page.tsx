'use client'

/**
 * 偏好设置(账户重组)· 纯偏好:涨跌色 + Bot 下单预设。
 *
 * 账户身份 / 会员 / 额度 / 兑换码 / 安全设置 已搬到「个人中心」(/account/membership)。
 * 路由保持 /account/profile 不变(只改标题 + 内容)。
 */

import { BotOrderPresetSection } from '@/components/settings/bot-order-preset-section'
import { ColorPrefSection } from '@/components/settings/color-pref-section'
import { DetailPrefsSection } from '@/components/settings/detail-prefs-section'
import { LanguageSection } from '@/components/settings/language-section'
import { ThemeSection } from '@/components/settings/theme-section'

export default function PreferencesPage() {
  return (
    <div>
      <h1 className="mb-6 font-serif text-2xl font-bold text-foreground">偏好设置</h1>
      {/* ★i18n:语言切换(显示类偏好聚一起·置 ThemeSection 前) */}
      <LanguageSection />
      <ThemeSection />
      <ColorPrefSection />
      <DetailPrefsSection />
      <BotOrderPresetSection />
    </div>
  )
}
