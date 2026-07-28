/**
 * 额度提示行(会员刀2)· 沙盘 / 回测共用,挂在提交按钮旁。
 *
 * 三态:加载/无数据 → 不渲染;有余量 → 灰字「今日剩 N/20 次」;
 * 耗尽 → 仅说明每日系统容量会自动重置，不展示商业升级入口。
 * 🔴 如实展示:剩几次是几次。纯展示组件(无 hook · 可 renderToString 测)。
 */

import type { QuotaItem } from '@/lib/api/quota'
import { EXHAUSTED_TEXT, isExhausted, quotaHintText } from '@/lib/quota-view'

export function QuotaHint({ item }: { item: QuotaItem | null }) {
  if (item === null) return null
  if (isExhausted(item)) {
    return (
      <span className="text-xs text-gold">{EXHAUSTED_TEXT}，明日自动恢复</span>
    )
  }
  return <span className="text-xs text-muted-foreground/70">{quotaHintText(item)}</span>
}
