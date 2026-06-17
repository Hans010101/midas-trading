/**
 * 头像选择器 · 编号 → 资源映射(集中一处)。
 *
 * ★ 设计资源到位后:只需替换 public/avatars/avatar-01.svg … avatar-16.svg 文件本身
 *   (保持文件名 + 本映射不变),渲染/选择器/保存逻辑无需再动。
 * NULL/0 = 默认邮箱首字母圆底;1-16 = 预设头像。零图片存储(后端只存编号)。
 */

export const AVATAR_COUNT = 16 // 与后端 app/api/v1/user.py _AVATAR_MAX 一致(改数量两处同步)

/** 是否为有效预设头像编号(1-16)· 类型守卫。 */
export function isPresetAvatar(id: number | null | undefined): id is number {
  return typeof id === 'number' && Number.isInteger(id) && id >= 1 && id <= AVATAR_COUNT
}

/** 预设头像资源路径(占位 SVG · 设计到位后替换同名文件)。 */
export function avatarSrc(id: number): string {
  return `/avatars/avatar-${String(id).padStart(2, '0')}.svg`
}

/** 选择器用:全部预设编号 [1..16]。 */
export const AVATAR_IDS: readonly number[] = Array.from({ length: AVATAR_COUNT }, (_, i) => i + 1)
