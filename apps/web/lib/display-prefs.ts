/**
 * 显示偏好(指标偏好系统 · 方案② 全浏览器 · 刀1)· 客户端 cookie 模块。
 *
 * ★独立于涨跌色 color_pref(那个保持不动)· 本模块用【独立新 cookie】display_prefs(JSON)·
 * 纯前端、零后端。沿用 color-pref 的 cookie 属性(path=/ · 1 年 · SameSite=Lax · 非 httpOnly ·
 * 客户端 JS 即时读写)。
 *
 * 消费方:刀2 详情页主图按本结构读 —— 指标图层开关(布林/缠论/MACD/做T)+ 默认周期。
 * 刀1 只【存】偏好(设置页写),不碰详情页。
 *
 * 容错:cookie 缺失 / JSON 损坏 / 字段缺失或类型错 → 一律降级【系统默认】,绝不崩(一贯容错纪律)。
 */

export interface IndicatorPrefs {
  boll: boolean
  chan: boolean
  macd: boolean
  dott: boolean
}

export interface DisplayPrefs {
  indicators: IndicatorPrefs
  /** 详情页默认周期 · 刀1 暴露 15m/1h/1d · 刀2 验回源后可加 5m/1w(故存为 string 前向兼容)。 */
  period: string
}

export const DISPLAY_PREFS_COOKIE = 'display_prefs'

// ★系统默认(游客 + 未设置用户都用这个)· 做T 默认【关】(dott:false)
export const DEFAULT_DISPLAY_PREFS: DisplayPrefs = {
  indicators: { boll: true, chan: true, macd: true, dott: false },
  period: '1h',
}

const MAX_AGE = 60 * 60 * 24 * 365 // 1 年 · 与 color_pref 一致

function asBool(v: unknown, fallback: boolean): boolean {
  return typeof v === 'boolean' ? v : fallback
}

/**
 * 把任意原始对象收敛为合法 DisplayPrefs(字段缺/类型错 → 用系统默认填)· 纯函数好测。
 * 任何不认识的输入(null/数组/字符串/缺字段)都安全降级到系统默认。
 */
export function coerceDisplayPrefs(raw: unknown): DisplayPrefs {
  const d = DEFAULT_DISPLAY_PREFS
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return { ...d, indicators: { ...d.indicators } }
  const obj = raw as Record<string, unknown>
  const ind = (obj.indicators && typeof obj.indicators === 'object' ? obj.indicators : {}) as Record<string, unknown>
  return {
    indicators: {
      boll: asBool(ind.boll, d.indicators.boll),
      chan: asBool(ind.chan, d.indicators.chan),
      macd: asBool(ind.macd, d.indicators.macd),
      dott: asBool(ind.dott, d.indicators.dott),
    },
    period: typeof obj.period === 'string' && obj.period ? obj.period : d.period,
  }
}

/** 读 display_prefs cookie → DisplayPrefs · 缺失/坏 JSON/字段缺 → 系统默认(容错不崩)。 */
export function readDisplayPrefs(): DisplayPrefs {
  if (typeof document === 'undefined') return { ...DEFAULT_DISPLAY_PREFS, indicators: { ...DEFAULT_DISPLAY_PREFS.indicators } }
  const m = document.cookie.match(/(?:^|;\s*)display_prefs=([^;]+)/)
  if (!m) return { ...DEFAULT_DISPLAY_PREFS, indicators: { ...DEFAULT_DISPLAY_PREFS.indicators } }
  try {
    return coerceDisplayPrefs(JSON.parse(decodeURIComponent(m[1])))
  } catch {
    return { ...DEFAULT_DISPLAY_PREFS, indicators: { ...DEFAULT_DISPLAY_PREFS.indicators } }
  }
}

/** 写 display_prefs cookie(JSON · encodeURIComponent · 沿用 color_pref 属性:path=/ · 1 年 · Lax)。 */
export function writeDisplayPrefs(prefs: DisplayPrefs): void {
  if (typeof document === 'undefined') return
  const v = encodeURIComponent(JSON.stringify(prefs))
  document.cookie = `${DISPLAY_PREFS_COOKIE}=${v}; path=/; max-age=${MAX_AGE}; SameSite=Lax`
}
