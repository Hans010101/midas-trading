/**
 * 涨跌色偏好(0023 阶段③ · 3.5 · 决策⑧)。
 *
 * 机制:0022 §2.2/§2.3 已就位 —— globals.css 定义 `--color-up/--color-down`
 * 默认红涨绿跌,`:root[data-color-pref="green-up"]` 翻转为绿涨红跌。
 * 本模块只管「偏好的读写 + 把偏好落到 <html data-color-pref>」。
 *
 * 持久化:**cookie**(非 DB)· 理由:
 *  - 根布局首屏前置内联脚本读 cookie 设 <html data-color-pref> → 无闪烁(ADR §7 目标)·
 *    用脚本而非 SSR 读 cookie:避免把 / 等 force-static 页打成 dynamic
 *  - 纯前端 · 零 PG 迁移 · 零后端改动 → 3.5 整期保持低风险
 *  - 取舍:按浏览器维度持久(非跨设备账号同步)· 对「显示偏好」类设置可接受,
 *    日后若要账号级同步,再单列一期(需 PG 迁移)升级。
 */

export type ColorPref = 'red-up' | 'green-up'

export const COLOR_PREF_COOKIE = 'color_pref'
export const DEFAULT_COLOR_PREF: ColorPref = 'red-up'
// 1 年 · 全站 · Lax(非 httpOnly · 客户端 JS 需即时读写)
const MAX_AGE = 60 * 60 * 24 * 365

/** 把任意原始值收敛为合法 ColorPref(非 green-up 一律默认红涨绿跌)。 */
export function parseColorPref(raw: string | undefined | null): ColorPref {
  return raw === 'green-up' ? 'green-up' : 'red-up'
}

/** 客户端读当前偏好:优先 <html data-color-pref>(SSR 已设)· 退回 cookie · 再退默认。 */
export function readColorPref(): ColorPref {
  if (typeof document === 'undefined') return DEFAULT_COLOR_PREF
  const attr = document.documentElement.dataset.colorPref
  if (attr) return parseColorPref(attr)
  const m = document.cookie.match(/(?:^|;\s*)color_pref=([^;]+)/)
  return parseColorPref(m ? decodeURIComponent(m[1]) : undefined)
}

/** 客户端即时应用偏好:写 cookie + 设 <html data-color-pref>(全产品涨跌色即时翻转,无需刷新)。 */
export function applyColorPref(pref: ColorPref): void {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.colorPref = pref
  document.cookie = `${COLOR_PREF_COOKIE}=${pref}; path=/; max-age=${MAX_AGE}; SameSite=Lax`
}
