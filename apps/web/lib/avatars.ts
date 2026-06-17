/**
 * 头像选择器 · 编号 → 资源映射(集中一处)。
 *
 * 真实设计头像已接入(2026-06 · 质检通过 · viewBox 0 0 512 512 · 自带圆底 · 品牌色)。
 * avatar_id → public/avatars/avatar-NN.svg → 设计来源:
 *   1-6   几何抽象 geo-01..06(同心/阶梯/矩阵/罗经/三角/双环)
 *   7-11  东方意象 east-01..05(山水/印章/祥云/铜钱/修竹)
 *   12-16 金融符号 fin-01..05(K线/趋势/牛/罗盘/阴阳)
 * NULL/0 = 默认邮箱首字母圆底。零图片存储(后端只存编号 avatar_id)。
 * ★ 换图只需替换同名 avatar-NN.svg 文件(本映射 + 渲染/选择器逻辑不变)。
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
