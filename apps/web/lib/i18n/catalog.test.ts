import { describe, expect, it } from 'vitest'

import enMessages from '@/messages/en.json'
import zhMessages from '@/messages/zh.json'

import {
  buildTranslationCatalog,
  translateCatalogText,
} from './catalog'

const catalog = buildTranslationCatalog(zhMessages, enMessages)

function messageKeys(
  value: Record<string, unknown>,
  prefix = '',
): string[] {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return child && typeof child === 'object' && !Array.isArray(child)
      ? messageKeys(child as Record<string, unknown>, path)
      : [path]
  })
}

describe('translation catalog', () => {
  it('keeps Chinese and English catalogs structurally identical', () => {
    expect(messageKeys(enMessages).sort()).toEqual(
      messageKeys(zhMessages).sort(),
    )
  })

  it('translates registered interface labels', () => {
    expect(translateCatalogText('用户管理', 'en', catalog)).toBe(
      'User Management',
    )
    expect(translateCatalogText('全球市场', 'en', catalog)).toBe(
      'Global Markets',
    )
  })

  it('preserves surrounding whitespace', () => {
    expect(translateCatalogText('  加载中…\n', 'en', catalog)).toBe(
      '  Loading…\n',
    )
  })

  it('tolerates historical spacing differences around punctuation', () => {
    expect(
      translateCatalogText('四市通览·点石成金', 'en', catalog),
    ).toBe('Global markets at a glance, turning insight into gold')
  })

  it('translates simple dynamic placeholders', () => {
    expect(
      translateCatalogText('已学 3/10', 'en', catalog),
    ).toBe('Completed 3/10')
    expect(
      translateCatalogText('布林做T 左移', 'en', catalog),
    ).toBe('Move Bollinger Day Trade left')
  })

  it('does not alter unregistered data or Chinese mode', () => {
    expect(translateCatalogText('腾讯控股', 'en', catalog)).toBe('腾讯控股')
    expect(translateCatalogText('用户管理', 'zh', catalog)).toBe('用户管理')
    expect(translateCatalogText('BTC/USDT', 'en', catalog)).toBe('BTC/USDT')
  })
})
