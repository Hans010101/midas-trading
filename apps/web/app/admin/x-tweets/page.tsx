'use client'

/**
 * 管理员 · X 营销每日推文(阶段4b · X 真发上线 2026-07-07)。
 *
 * ★ 安全边界后端 AdminDep(403)· 数据全来自 admin API,普通用户手输 URL → 后端 403 → 降级。
 * 流程(Hans 重构 2026-07-08):草稿由后台每 15min 自动生成好(带图)→ 顶部「币安广场/X 推文」
 *   两 tab 只【切换查看】对应平台已生成草稿(不触发生成)→ 审 → 发布;手动生成弱化为「＋立即补充生成」。
 * ★ 发布:门禁通过的推文可【admin 单次点】发布到 币安广场 / X(tweepy OAuth 1.0a)· 各自状态/按钮。
 *   含 URL 的推有成本提醒(X $0.20 ≈ 十几倍)。
 * ★ 截图:xshot 异步回填 image_path → 列表轮询(近 20min 有缺图行 · 12s)自动刷出 → blob 显图。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useEffect, useMemo, useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { AutoPilotPanel } from '@/components/admin/auto-pilot-panel'
import { TopNav } from '@/components/layout/top-nav'
import {
  fetchXTweetImage,
  fetchXTweets,
  generateXTweets,
  publishXTweet,
  type XTweetItem,
} from '@/lib/api/x-tweets'

function fmtTime(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(
    d.getHours(),
  ).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function compact(value: number | null): string {
  return value === null ? '—' : new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function BiasBadge({ bias }: { bias: string }) {
  return (
    <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{bias}</span>
  )
}

const CONTENT_LABEL: Record<XTweetItem['content_type'], string> = {
  market_analysis: 'K 线分析',
  news: '热点快讯',
  whale: '大额资金',
  unlock: '代币解锁',
}

/** K线主图截图:★端点 AdminDep → authed fetch blob → objectURL → <img>。无图/未截好显占位。
 *
 * ★配图修复(2026-07-08):旧版 useEffect 一次性 fetch——瞬时失败/挂起 = 永久占位、无重试、
 * 不随列表轮询自愈。改 React Query:失败自动重试 ×2 · staleTime=Infinity(截图内容不变,
 * 拿到就不再打端点)· 列表轮询刷出 image_path 后 hasImage 翻真 → enabled 生效自动拉图。
 */
function XTweetImage({ id, hasImage, token }: { id: number; hasImage: boolean; token: string }) {
  const imgQuery = useQuery({
    queryKey: ['admin-x-tweet-image', id],
    queryFn: () => fetchXTweetImage(token, id),
    enabled: hasImage && token !== '',
    staleTime: Infinity,
    retry: 2, // ★瞬时网络失败自动重试(旧版一次失败=永久「读取失败」)
  })
  // blob → objectURL(随 blob 重建 · 卸载/更换时 revoke 防内存泄漏)
  const url = useMemo(
    () => (imgQuery.data ? URL.createObjectURL(imgQuery.data) : ''),
    [imgQuery.data],
  )
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url)
    },
    [url],
  )

  if (!hasImage || imgQuery.isError) {
    return (
      <div className="flex h-32 items-center justify-center rounded-md border border-dashed border-paper text-xs text-muted-foreground">
        {hasImage ? '截图读取失败' : '截图生成中…(截好自动显示)'}
      </div>
    )
  }
  if (!url) {
    return (
      <div className="flex h-32 items-center justify-center rounded-md border border-paper text-xs text-muted-foreground">
        载入截图…
      </div>
    )
  }
  // eslint-disable-next-line @next/next/no-img-element -- blob objectURL,非静态资源,不走 next/image
  return <img src={url} alt="K线主图截图" className="w-full rounded-md border border-paper" />
}

/** 发布行(★仅门禁通过的推文显)· 每平台一个状态/按钮 · admin 单次显式点 → 异步发。 */
function PublishRow({
  t,
  token,
  onChange,
}: {
  t: XTweetItem
  token: string
  onChange: () => void
}) {
  const [err, setErr] = useState('')
  const mut = useMutation({
    mutationFn: (platform: string) => publishXTweet(token, t.id, platform, t.account_key),
    onSuccess: () => {
      setErr('')
      onChange() // 异步发布 pending → 稍后补刷一次拿 success/failed
      setTimeout(onChange, 8000)
    },
    onError: (e: Error) => setErr(e.message),
  })
  const binance = t.dispatches.find((d) => d.platform === 'binance_square')
  const x = t.dispatches.find((d) => d.platform === 'x')
  // ★per-platform 发布中:共享一个 mutation,用 mut.variables 分清点的是哪个平台
  const sendingPlatform = mut.isPending ? (mut.variables ?? null) : null
  const binanceSending = sendingPlatform === 'binance_square' || binance?.status === 'pending'
  const xSending = sendingPlatform === 'x' || x?.status === 'pending'
  // ★改进3:按 gen_style 分离发布选项 —— x_short 只显「发布到 X」· default 只显「发布到币安广场」
  //   (K线图两边共用同一次扫描的截图,不冲突)。
  const isX = t.gen_style === 'x_short'
  const disp = isX ? x : binance
  // ★审计:有发布记录则标来源(自动托管 PR-4)· auto 自动托管 / manual 人工点
  const sourceBadge = disp ? (
    <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
      {disp.source === 'auto' ? '🤖 自动' : '👤 人工'}
    </span>
  ) : null

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-paper pt-2">
      <span className="text-xs text-muted-foreground">发布到:</span>
      {sourceBadge}
      {!isX && (binance?.status === 'success' ? (
        <>
          <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
            ✓ 币安广场
            {binance.url && (
              <a href={binance.url} target="_blank" rel="noopener noreferrer" className="ml-1 underline">
                查看
              </a>
            )}
          </span>
          <span className="text-xs text-muted-foreground">
            {binance.metrics_updated_at
              ? `阅读 ${compact(binance.view_count)} · 点赞 ${compact(binance.like_count)} · 评论 ${compact(binance.comment_count)} · 分享 ${compact(binance.share_count)}`
              : '互动数据待首次同步'}
          </span>
        </>
      ) : binanceSending ? (
        <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          币安广场 发布中…
        </span>
      ) : (
        <button
          type="button"
          onClick={() => mut.mutate('binance_square')}
          className="rounded-md bg-gold px-2.5 py-1 text-xs font-medium text-white hover:bg-gold/85"
        >
          {binance?.status === 'failed' ? '重试币安广场' : '发布到币安广场'}
        </button>
      ))}
      {/* ★改进3:X 短推(gen_style=x_short)底部只显「发布到 X」· tweepy OAuth 1.0a 真发 */}
      {isX && (x?.status === 'success' ? (
        <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
          ✓ X
          {x.url && (
            <a href={x.url} target="_blank" rel="noopener noreferrer" className="ml-1 underline">
              查看
            </a>
          )}
        </span>
      ) : xSending ? (
        <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">X 发布中…</span>
      ) : (
        <button
          type="button"
          onClick={() => mut.mutate('x')}
          className="rounded-md bg-midas-red px-2.5 py-1 text-xs font-medium text-white hover:bg-midas-red/85"
        >
          {x?.status === 'failed' ? '重试发布到 X' : '发布到 X'}
        </button>
      ))}
      {/* ★URL 成本提醒仅 X 短推显(链接税是 X 特有)· 含链接推 $0.20 ≈ 十几倍 */}
      {isX && t.has_url && (
        <span
          className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-700"
          title="含链接的推 $0.20/条 ≈ 无链接($0.015)的十几倍 · 建议链接放简介 / 评论区,正文别放"
        >
          ⚠ 正文含链接(发 X 贵十几倍)
        </span>
      )}
      {!isX && binance?.status === 'failed' && binance.error && (
        <span className="w-full text-xs text-red-600">币安失败:{binance.error}</span>
      )}
      {isX && x?.status === 'failed' && x.error && (
        <span className="w-full text-xs text-red-600">X 失败:{x.error}</span>
      )}
      {err && <span className="w-full text-xs text-red-600">{err}</span>}
    </div>
  )
}

function TweetCard({
  t,
  token,
  onChange,
}: {
  t: XTweetItem
  token: string
  onChange: () => void
}) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="font-mono text-sm font-bold">{t.symbol}</span>
        <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
          {t.account_key === 'legacy_midas' ? '点金' : '点金雷达'}
        </span>
        <BiasBadge bias={t.bias} />
        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[11px] font-medium text-blue-700">
          {CONTENT_LABEL[t.content_type]}
        </span>
        {/* ★内容风格/平台标识(step1 分平台)· x_short=专为 X 生成的短推 */}
        {t.gen_style === 'x_short' && (
          <span className="rounded bg-midas-red/15 px-1.5 py-0.5 text-[11px] font-medium text-midas-red">
            𝕏 短推
          </span>
        )}
        {/* ★自动托管起草素材标识(频率调整)· 第2条未自动发=可人工补发 */}
        {t.auto_drafted && (
          <span className="rounded bg-gold/15 px-1.5 py-0.5 text-[11px] font-medium text-gold">
            🤖 自动起草
          </span>
        )}
        <span className="ml-auto font-mono text-xs text-muted-foreground">
          {fmtTime(t.created_at)}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{t.tweet_text}</p>
      {t.content_type === 'market_analysis' && (
        <div className="mt-3">
          <XTweetImage id={t.id} hasImage={t.image_path !== null} token={token} />
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-paper pt-2">
        {t.compliance_passed ? (
          <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
            ✓ 门禁通过
          </span>
        ) : (
          <span className="rounded bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
            ✕ 门禁拦截 · 不可发
          </span>
        )}
        <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {t.status === 'draft' ? '待发' : t.status}
        </span>
        {!t.compliance_passed && t.compliance_reason && (
          <span className="w-full text-xs text-red-600">原因:{t.compliance_reason}</span>
        )}
      </div>
      {/* ★发布行:仅门禁通过的可发(不过的上面已标「不可发」)· admin 单次显式点 */}
      {t.compliance_passed && <PublishRow t={t} token={token} onChange={onChange} />}
    </div>
  )
}

export default function AdminXTweetsPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()
  const [note, setNote] = useState<string>('')
  // ★查看 tab(gen_style)· 切换只筛选查看已自动生成的草稿,不触发生成(Hans 重构:动作→查看)
  const [tab, setTab] = useState<'default' | 'x_short'>('default')
  const [squareAccount, setSquareAccount] = useState<'midas_trading' | 'legacy_midas'>(
    'midas_trading',
  )

  const query = useQuery({
    queryKey: ['admin-x-tweets'],
    queryFn: ({ signal }) => fetchXTweets(token, signal),
    enabled: token !== '',
    // ★配图轮询(2026-07-08):近 20 分钟内还有未截好图的推 → 12s 一刷(截图串行 10-15s/张·
    //   异步回填 image_path);全部有图 / 超窗(截图彻底失败的老行)→ 返回 false 自动停,不空转。
    refetchInterval: (q) => {
      const items = q.state.data?.items ?? []
      const cutoff = Date.now() - 20 * 60_000
      const waiting = items.some(
        (t) => t.content_type === 'market_analysis' && t.status === 'published' &&
          t.image_path === null && new Date(t.created_at).getTime() > cutoff,
      )
      return waiting ? 12_000 : false
    },
  })

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['admin-x-tweets'] })

  const genMut = useMutation({
    mutationFn: (style: 'default' | 'x_short') =>
      generateXTweets(token, style, squareAccount),
    onSuccess: (res) => {
      setNote(res.message)
      // ★异步生成约数十秒 · 先刷一次,再延时补刷一次(覆盖 worker 跑完)
      invalidate()
      setTimeout(invalidate, 35000)
    },
    onError: () => setNote('触发失败,请重试'),
  })

  const forbidden = query.isError
  const items: XTweetItem[] = query.data?.items ?? []
  // ★按平台(gen_style)分两条线 · tab 只切换查看,数据本来就带 gen_style
  const binanceItems = items.filter(
    (t) => t.gen_style !== 'x_short' && t.account_key === squareAccount,
  )
  const xItems = items.filter((t) => t.gen_style === 'x_short')
  const visible = tab === 'x_short' ? xItems : binanceItems
  const passed = visible.filter((t) => t.compliance_passed).length

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <AdminNav />

        {forbidden ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center shadow-sm">
            <p className="text-sm text-muted-foreground">该页面仅管理员可见。</p>
            <Link
              href="/global"
              className="mt-3 inline-block rounded-md bg-midas-red px-4 py-1.5 text-sm text-white hover:bg-midas-red/90"
            >
              返回首页
            </Link>
          </div>
        ) : (
          <>
            {/* ★自动托管控制面板(开关/熔断/配额/时段)· 自动托管 PR-4 */}
            <AutoPilotPanel token={token} />

            {tab === 'default' && (
              <div className="mb-3 flex items-center gap-1 rounded-md bg-muted p-1">
                {([
                  ['midas_trading', '点金雷达'],
                  ['legacy_midas', '点金'],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSquareAccount(key)}
                    className={squareAccount === key
                      ? 'rounded bg-cream px-3 py-1.5 text-sm font-medium shadow-sm'
                      : 'rounded px-3 py-1.5 text-sm text-muted-foreground'}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}

            {/* ★查看 tab(Hans 重构):顶部两个 tab 只切换查看对应平台已【自动生成】的草稿,
                不触发生成。草稿由后台每 15 分钟(:04/:19/:34/:49)自动生成好(带图),打开即见现成的。 */}
            <div className="mb-4 flex flex-wrap items-center gap-1 border-b border-paper">
              {(
                [
                  { key: 'default' as const, label: '币安广场', count: binanceItems.length },
                  { key: 'x_short' as const, label: '𝕏 X 推文', count: xItems.length },
                ]
              ).map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTab(t.key)}
                  className={
                    tab === t.key
                      ? '-mb-px border-b-2 border-midas-red px-4 py-2 text-sm font-medium text-midas-red'
                      : '-mb-px border-b-2 border-transparent px-4 py-2 text-sm text-muted-foreground hover:text-foreground'
                  }
                >
                  {t.label}
                  <span className="ml-1.5 text-xs">({t.count})</span>
                </button>
              ))}
              <div className="ml-auto flex items-center gap-2 py-1">
                <span className="text-xs text-muted-foreground">
                  门禁通过 {passed} · 最近 72h
                </span>
                {/* ★手动生成弱化为次要「立即补充生成」(主路径是后台自动生成·这里只补一批) */}
                <button
                  type="button"
                  onClick={() => genMut.mutate(tab)}
                  disabled={genMut.isPending || token === ''}
                  title="草稿本由后台每 15 分钟自动生成 · 这里可立即补充生成一批当前平台的草稿"
                  className="rounded-md border border-paper px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  {genMut.isPending ? '生成中…' : '＋ 立即补充生成'}
                </button>
                <button
                  type="button"
                  onClick={invalidate}
                  className="rounded-md border border-paper px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                >
                  刷新
                </button>
              </div>
            </div>

            {note && (
              <p className="mb-4 rounded-md bg-gold/10 px-3 py-2 text-xs text-muted-foreground">
                {note}
              </p>
            )}

            {query.isLoading ? (
              <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
            ) : visible.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                {tab === 'x_short' ? '𝕏 X 推文' : '币安广场'}暂无草稿 ·
                后台每 15 分钟(整点后 :04/:19/:34/:49)自动生成(需自动托管开关开启)· 或点「＋ 立即补充生成」。
              </p>
            ) : (
              <div className="space-y-3">
                {visible.map((t) => (
                  <TweetCard key={t.id} t={t} token={token} onChange={invalidate} />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
