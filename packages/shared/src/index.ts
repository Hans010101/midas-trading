// 点金 Midas · 前后端共享类型契约
// M0 阶段:手写匹配 apps/api/app/schemas/market.py 的 Pydantic v2 schema
// Task 1.1 剩余项会用 openapi-typescript 从 FastAPI 自动生成,届时替换本文件

export const SHARED_PACKAGE_VERSION = '0.1.0' as const

// =====================
// 市场与周期(Pydantic Literal 类型对应)
// =====================

export type Market = 'cn' | 'us' | 'crypto' | 'hk'
export type Period = '1m' | '5m' | '15m' | '30m' | '1h' | '1d' | '1w'

export const MARKETS = ['cn', 'us', 'crypto', 'hk'] as const satisfies readonly Market[]
export const PERIODS = ['1m', '5m', '15m', '30m', '1h', '1d', '1w'] as const satisfies readonly Period[]

// =====================
// K 线 + 标的元信息
// =====================

export interface Kline {
  /** ISO 8601 UTC datetime, e.g. "2026-05-19T07:00:00Z" */
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  /** 成交额(单位:报价货币 / RMB / USD)· ccxt 和 yfinance 不提供时为 null */
  amount: number | null
}

export interface KlineResponse {
  symbol: string
  market: Market
  period: Period
  items: Kline[]
}

export interface SymbolMeta {
  symbol: string
  market: Market
  name: string
  name_en: string
  /** ISO 8601 date string, e.g. "2001-08-27";未提供时为 null */
  listed_date: string | null
  is_active: boolean
  /** ISO 8601 UTC datetime */
  updated_at: string
}
