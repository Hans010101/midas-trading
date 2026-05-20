'use client'

/**
 * 右栏 · 真实自选股(0007 设计)。
 *
 * - useWatchlist:GET /api/v1/watchlist(空 + email_verified → 后端预填 3 demo)
 * - useWatchlistQuotes:30s 轮询每个标的最新价 + 涨跌幅
 * - @dnd-kit/sortable:拖拽 reorder(乐观更新 + 失败回滚)
 * - 删除按钮 hover 浮现 · 一键删
 * - Cmd/Ctrl+K → SymbolSearchDialog(加自选)
 * - 空态卡(0005 风格)· 米白卡 + 📋 + 中国红 CTA
 * - 下方保留 AI 决策卡占位(M1)
 */

import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { VirtualBadge } from '@/components/ui/virtual-badge'
import { SymbolSearchDialog } from '@/components/workbench/symbol-search-dialog'
import {
  useDeleteFromWatchlist,
  useReorderWatchlist,
  useWatchlist,
} from '@/hooks/use-watchlist'
import { useWatchlistQuotes, type Quote } from '@/hooks/use-watchlist-quotes'
import type { WatchlistItem } from '@/lib/api/watchlist'
import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

const MARKET_LABEL: Record<Market, string> = {
  cn: 'A 股',
  us: '美股',
  crypto: '加密',
}

function chipClass(m: Market): string {
  if (m === 'cn') return 'text-midas-red border-midas-red/30 bg-midas-red-glow/30'
  if (m === 'us') return 'text-foreground border-paper bg-paper/50'
  return 'text-gold border-gold/30 bg-gold/10'
}

export function WatchlistColumn() {
  const { data: items = [], isLoading } = useWatchlist()
  const reorderMutation = useReorderWatchlist()
  const [searchOpen, setSearchOpen] = useState(false)
  const setMarket = useWorkbenchStore((s) => s.setMarket)
  const setSymbol = useWorkbenchStore((s) => s.setSymbol)
  const currentSymbol = useWorkbenchStore((s) => s.symbol)

  const sortedItems = useMemo(
    () => [...items].sort((a, b) => a.sort_order - b.sort_order),
    [items],
  )

  const quotes = useWatchlistQuotes(sortedItems)

  // 全局 Cmd/Ctrl+K → 打开 search dialog
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  )

  const onDragEnd = useCallback(
    (e: DragEndEvent) => {
      if (!e.over || e.active.id === e.over.id) return
      const oldIndex = sortedItems.findIndex((i) => i.id === e.active.id)
      const newIndex = sortedItems.findIndex((i) => i.id === e.over!.id)
      if (oldIndex === -1 || newIndex === -1) return
      const newOrder = arrayMove(sortedItems, oldIndex, newIndex)
      reorderMutation.mutate(newOrder.map((i) => i.id))
    },
    [sortedItems, reorderMutation],
  )

  const onSelectSymbol = useCallback(
    (item: WatchlistItem) => {
      setMarket(item.market)
      setSymbol(item.symbol)
    },
    [setMarket, setSymbol],
  )

  return (
    <aside className="flex w-[280px] shrink-0 flex-col border-l border-midas-red bg-background">
      {/* 标题 + 添加按钮 */}
      <section className="border-b border-paper px-3 py-2.5">
        <div className="flex items-center justify-between">
          <h2 className="font-serif text-sm font-bold text-foreground">自选股</h2>
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className="flex items-center gap-1 rounded-md border border-paper bg-cream px-2 py-1 text-xs text-foreground transition-colors hover:border-midas-red hover:bg-midas-red-glow/40"
            title="搜索标的 (⌘K / Ctrl+K)"
          >
            <Plus className="h-3 w-3" />
            <span>添加</span>
            <kbd className="ml-1 hidden font-mono text-[9px] text-muted-foreground sm:inline">
              ⌘K
            </kbd>
          </button>
        </div>
      </section>

      {/* 列表 / 空态 */}
      <section className="flex-1 overflow-y-auto p-3">
        {isLoading ? (
          <div className="py-8 text-center text-xs text-muted-foreground/60">载入中…</div>
        ) : sortedItems.length === 0 ? (
          <WatchlistEmpty onSearch={() => setSearchOpen(true)} />
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={onDragEnd}
          >
            <SortableContext
              items={sortedItems.map((i) => i.id)}
              strategy={verticalListSortingStrategy}
            >
              <ul className="space-y-1.5">
                {sortedItems.map((item, idx) => (
                  <SortableRow
                    key={item.id}
                    item={item}
                    quote={quotes[idx]}
                    selected={item.symbol === currentSymbol}
                    onSelect={() => onSelectSymbol(item)}
                  />
                ))}
              </ul>
            </SortableContext>
          </DndContext>
        )}
      </section>

      {/* AI 决策卡占位(M1)*/}
      <div className="border-t border-paper" />
      <section className="p-3">
        <div className="rounded-md border border-dashed border-paper bg-cream p-4 text-center">
          <div className="mb-2 flex justify-center">
            <VirtualBadge size="sm" />
          </div>
          <p className="font-serif text-sm font-bold text-foreground">AI 决策卡</p>
          <p className="mt-1 text-xs text-muted-foreground/70">M1 待实装(缠论 + LLM)</p>
        </div>
      </section>

      <SymbolSearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
    </aside>
  )
}

function WatchlistEmpty({ onSearch }: { onSearch: () => void }) {
  return (
    <div className="mt-4 flex flex-col items-center justify-center rounded-md border border-paper bg-cream p-6 text-center">
      <span className="mb-3 text-3xl opacity-40" aria-hidden="true">
        📋
      </span>
      <p className="mb-1 font-serif text-sm font-bold text-foreground">还没有自选股</p>
      <p className="mb-4 text-xs text-muted-foreground/70">搜索一只标的开始关注</p>
      <button
        type="button"
        onClick={onSearch}
        className="rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-midas-red-deep"
      >
        搜索标的
      </button>
      <p className="mt-2 font-mono text-[10px] text-muted-foreground/60">⌘K / Ctrl+K</p>
    </div>
  )
}

interface SortableRowProps {
  item: WatchlistItem
  quote?: Quote
  selected: boolean
  onSelect: () => void
}

function SortableRow({ item, quote, selected, onSelect }: SortableRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.id })
  const deleteMutation = useDeleteFromWatchlist()

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  const changePct = quote?.changePct
  const isUp = changePct != null && changePct > 0
  const isDown = changePct != null && changePct < 0

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={cn(
        'group relative flex items-center gap-1.5 rounded-md border px-2 py-2 transition-colors',
        selected
          ? 'border-midas-red bg-midas-red-glow/30'
          : 'border-paper bg-cream hover:border-midas-red/40',
        isDragging && 'shadow-md',
      )}
    >
      {/* 拖拽手柄 */}
      <button
        type="button"
        className="cursor-grab text-muted-foreground/40 hover:text-muted-foreground active:cursor-grabbing"
        aria-label="拖拽排序"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" />
      </button>

      {/* 主体可点 · 切到该标的 */}
      <button
        type="button"
        onClick={onSelect}
        className="flex flex-1 items-center justify-between gap-2 text-left"
      >
        <div className="flex min-w-0 flex-col">
          <span className="truncate font-mono text-xs font-medium text-foreground">
            {item.symbol}
          </span>
          <span
            className={cn(
              'mt-0.5 self-start rounded border px-1 text-[9px] leading-tight',
              chipClass(item.market),
            )}
          >
            {MARKET_LABEL[item.market]}
          </span>
        </div>
        <div className="text-right">
          <div className="font-mono text-xs tabular-nums text-foreground">
            {quote?.close != null ? formatPrice(quote.close) : '—'}
          </div>
          <div
            className={cn(
              'font-mono text-[10px] tabular-nums',
              isUp && 'text-bull',
              isDown && 'text-bear',
              !isUp && !isDown && 'text-muted-foreground/60',
            )}
          >
            {changePct != null ? formatPct(changePct) : '—'}
          </div>
        </div>
      </button>

      {/* 删除按钮 · hover 浮现 */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          deleteMutation.mutate(item.id)
        }}
        className="opacity-0 transition-opacity hover:text-midas-red focus:opacity-100 group-hover:opacity-100"
        aria-label={`删除 ${item.symbol}`}
        disabled={deleteMutation.isPending}
      >
        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
      </button>
    </li>
  )
}

function formatPrice(p: number): string {
  if (p < 10) return p.toFixed(4)
  return p.toFixed(2)
}

function formatPct(p: number): string {
  const sign = p >= 0 ? '+' : ''
  return `${sign}${p.toFixed(2)}%`
}
