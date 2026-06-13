/**
 * 额度提示行(会员刀2)· 沙盘 / 回测共用,挂在提交按钮旁。
 *
 * 三态:加载/无数据 → 不渲染;有余量 → 灰字「今日剩 N/20 次」;
 * 耗尽 → 文案 + 「了解进阶版 →」指官网 /#membership(会员接口区首个流量)。
 * 🔴 如实展示:剩几次是几次。纯展示组件(无 hook · 可 renderToString 测)。
 */

import Link from 'next/link'

import type { QuotaItem } from '@/lib/api/quota'
import { EXHAUSTED_TEXT, isExhausted, quotaHintText } from '@/lib/quota-view'

export function QuotaHint({ item }: { item: QuotaItem | null }) {
  if (item === null) return null
  if (isExhausted(item)) {
    return (
      <span className="text-xs text-gold">
        {EXHAUSTED_TEXT}
        <Link href="/#membership" className="ml-1.5 text-midas-red hover:underline">
          了解进阶版 →
        </Link>
      </span>
    )
  }
  return <span className="text-xs text-muted-foreground/70">{quotaHintText(item)}</span>
}
