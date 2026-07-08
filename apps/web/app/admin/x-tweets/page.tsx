'use client'

/**
 * 管理员 · X 营销每日推文(阶段4b · X 真发上线 2026-07-07)。
 *
 * ★ 安全边界后端 AdminDep(403)· 数据全来自 admin API,普通用户手输 URL → 后端 403 → 降级。
 * 流程:点「生成今日推文」→ 后端异步选币+DeepSeek生成+门禁 → 列表展示(★门禁不过的也列,标红不可发)。
 * ★ 发布:门禁通过的推文可【admin 单次点】发布到 币安广场 / X(tweepy OAuth 1.0a)· 各自状态/按钮。
 *   含 URL 的推有成本提醒(X $0.20 ≈ 十几倍)· 截图(image_path)PR-4 才有,现阶段不显图。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useEffect, useState } from 'react'

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

function BiasBadge({ bias }: { bias: string }) {
  return (
    <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{bias}</span>
  )
}

/** K线主图截图:★端点 AdminDep → authed fetch blob → objectURL → <img>。无图/未截好显占位。 */
function XTweetImage({ id, hasImage, token }: { id: number; hasImage: boolean; token: string }) {
  const [url, setUrl] = useState<string>('')
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!hasImage || token === '') return
    let revoked = ''
    let alive = true
    fetchXTweetImage(token, id)
      .then((blob) => {
        if (!alive) return
        revoked = URL.createObjectURL(blob)
        setUrl(revoked)
      })
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [id, hasImage, token])

  if (!hasImage || failed) {
    return (
      <div className="flex h-32 items-center justify-center rounded-md border border-dashed border-paper text-xs text-muted-foreground">
        {hasImage ? '截图读取失败' : '截图生成中…(异步,稍后刷新)'}
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
    mutationFn: (platform: string) => publishXTweet(token, t.id, platform),
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
        <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
          ✓ 币安广场
          {binance.url && (
            <a href={binance.url} target="_blank" rel="noopener noreferrer" className="ml-1 underline">
              查看
            </a>
          )}
        </span>
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
        <BiasBadge bias={t.bias} />
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
      <div className="mt-3">
        <XTweetImage id={t.id} hasImage={t.image_path !== null} token={token} />
      </div>
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

  const query = useQuery({
    queryKey: ['admin-x-tweets'],
    queryFn: ({ signal }) => fetchXTweets(token, signal),
    enabled: token !== '',
  })

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['admin-x-tweets'] })

  const genMut = useMutation({
    mutationFn: (style: 'default' | 'x_short') => generateXTweets(token, style),
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
  const passed = items.filter((t) => t.compliance_passed).length

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

            <div className="mb-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => genMut.mutate('default')}
                disabled={genMut.isPending || token === ''}
                className="rounded-md bg-gold px-4 py-1.5 text-sm font-medium text-white hover:bg-gold/90 disabled:opacity-50"
              >
                {genMut.isPending && genMut.variables === 'default' ? '触发中…' : '生成长文(币安广场)'}
              </button>
              {/* ★step1:专为 X 生成的短推(≤110 字·冷静体检口吻)· 与长文分平台各生成一套 */}
              <button
                type="button"
                onClick={() => genMut.mutate('x_short')}
                disabled={genMut.isPending || token === ''}
                className="rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white hover:bg-midas-red/90 disabled:opacity-50"
              >
                {genMut.isPending && genMut.variables === 'x_short' ? '触发中…' : '𝕏 生成 X 短推'}
              </button>
              <button
                type="button"
                onClick={invalidate}
                className="rounded-md border border-paper px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
              >
                刷新
              </button>
              <span className="ml-auto text-xs text-muted-foreground">
                共 {items.length} 条 · 门禁通过 {passed} 条 · 仅显最近 72h
              </span>
            </div>

            {note && (
              <p className="mb-4 rounded-md bg-gold/10 px-3 py-2 text-xs text-muted-foreground">
                {note}
              </p>
            )}

            {query.isLoading ? (
              <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
            ) : items.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                还没有推文 · 点「生成今日推文」开始(异步,约数十秒后刷新可见)。
              </p>
            ) : (
              <div className="space-y-3">
                {items.map((t) => (
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
