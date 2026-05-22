'use client'

/**
 * Crypto Pro 合约维度 TanStack Query hooks(M2-D 接真实数据)。
 *
 * - retry: 0(项目铁律 · 后端 BaseDataSource 已在 transport 层重试)
 * - staleTime 60s(OI/多空比 5min 栅格 · 1 分钟内复用缓存)
 * - enabled 由调用方控制
 *
 * 错误/空数据交给调用方 UI 处理(显示「暂无数据」占位 · 不伪造)。
 */

import { useQuery } from '@tanstack/react-query'

import {
  fetchFundingRate,
  fetchFuturesInfo,
  fetchLongShortRatio,
  fetchOpenInterest,
  type FundingRateResponse,
  type FuturesSymbolInfo,
  type LongShortRatioResponse,
  type OpenInterestResponse,
} from '@/lib/api/crypto'

const STALE = 60_000

export function useOpenInterest(symbol: string, limit = 96, enabled = true) {
  return useQuery<OpenInterestResponse>({
    queryKey: ['crypto-oi', symbol, limit],
    queryFn: ({ signal }) => fetchOpenInterest(symbol, limit, signal),
    enabled,
    retry: 0,
    staleTime: STALE,
  })
}

export function useLongShortRatio(symbol: string, limit = 96, enabled = true) {
  return useQuery<LongShortRatioResponse>({
    queryKey: ['crypto-lsr', symbol, limit],
    queryFn: ({ signal }) => fetchLongShortRatio(symbol, limit, signal),
    enabled,
    retry: 0,
    staleTime: STALE,
  })
}

export function useFundingRate(symbol: string, limit = 100, enabled = true) {
  return useQuery<FundingRateResponse>({
    queryKey: ['crypto-funding', symbol, limit],
    queryFn: ({ signal }) => fetchFundingRate(symbol, limit, signal),
    enabled,
    retry: 0,
    staleTime: STALE,
  })
}

export function useFuturesInfo(symbol: string, enabled = true) {
  return useQuery<FuturesSymbolInfo>({
    queryKey: ['crypto-info', symbol],
    queryFn: ({ signal }) => fetchFuturesInfo(symbol, signal),
    enabled,
    retry: 0,
    staleTime: STALE,
  })
}
