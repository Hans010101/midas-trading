import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'

const DATABASE = 'midas-trading-db'
const DETAIL_ENDPOINT =
  'https://www.binance.com/bapi/composite/v3/friendly/pgc/special/content/detail'
const USER_ENDPOINT =
  'https://www.binance.com/bapi/composite/v3/friendly/pgc/user/client'
const PROFILE_CONTENT_ENDPOINT =
  'https://www.binance.com/bapi/composite/v2/friendly/pgc/content/queryUserProfilePageContentsWithFilter'

function quote(value) {
  if (value === null || value === undefined) return 'NULL'
  if (typeof value === 'number') return String(value)
  return `'${String(value).replaceAll("'", "''")}'`
}

function query(sql) {
  const output = execFileSync(
    'pnpm',
    [
      '--filter', '@midas-trading/cloudflare-api', 'exec', 'wrangler', 'd1',
      'execute', DATABASE, '--remote', '--json', '--command', sql,
    ],
    { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 },
  )
  const start = output.indexOf('[')
  const end = output.lastIndexOf(']')
  if (start < 0 || end < start) throw new Error('D1 未返回 JSON 结果')
  return JSON.parse(output.slice(start, end + 1))
    .flatMap((batch) => batch.results ?? [])
}

function postIdFrom(url, storedId) {
  if (storedId) return String(storedId)
  return /(?:\/cpos\/|\/post\/)(\d+)/u.exec(url ?? '')?.[1] ?? null
}

function count(value) {
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? Math.trunc(number) : null
}

function postMetrics(data) {
  if (!data || typeof data !== 'object') return null
  const postId = data.id === undefined ? null : String(data.id)
  const squareUid = typeof data.squareUid === 'string' ? data.squareUid : null
  if (!postId || !squareUid) return null
  return {
    postId,
    squareUid,
    views: count(data.viewCount),
    likes: count(data.likeCount),
    comments: count(data.commentCount),
    shares: count(data.shareCount),
  }
}

function profilePage(data) {
  const posts = Array.isArray(data?.contents) ? data.contents.flatMap((item) => {
    const postId = item?.id === undefined ? null : String(item.id)
    const createdAt = count(item?.createTime)
    const views = count(item?.viewCount)
    return postId && createdAt !== null && views !== null ? [{ postId, createdAt, views }] : []
  }) : []
  const nextOffset = count(data?.timeOffset)
  return { posts, nextOffset }
}

async function binanceJson(url, init) {
  const response = await fetch(url, {
    ...init,
    headers: {
      accept: 'application/json',
      'user-agent': 'Mozilla/5.0 (compatible; MidasTradingMetrics/1.0)',
      ...(init?.headers ?? {}),
    },
    signal: AbortSignal.timeout(20_000),
  })
  const body = await response.json()
  if (!response.ok || body?.code !== '000000') {
    throw new Error(`币安接口拒绝 [${body?.code ?? response.status}]`)
  }
  return body.data
}

async function historicalMetrics(squareUid, trackedPostIds, since) {
  let offset = -1
  let totalViews = 0
  let views7d = 0
  const seenOffsets = new Set()

  for (let pageNumber = 1; pageNumber <= 500; pageNumber += 1) {
    const params = new URLSearchParams({
      targetSquareUid: squareUid,
      timeOffset: String(offset),
      filterType: 'ALL',
    })
    const page = profilePage(await binanceJson(`${PROFILE_CONTENT_ENDPOINT}?${params}`))
    if (page.posts.length === 0) return { totalViews, views7d, pages: pageNumber - 1 }
    for (const post of page.posts) {
      if (trackedPostIds.has(post.postId)) continue
      totalViews += post.views
      if (post.createdAt >= since) views7d += post.views
    }
    if (page.nextOffset === null || seenOffsets.has(page.nextOffset)) {
      throw new Error('币安历史内容分页游标无效')
    }
    seenOffsets.add(page.nextOffset)
    offset = page.nextOffset
  }
  throw new Error('币安历史内容超过 500 页，已停止同步')
}

async function main() {
  const now = Date.now()
  const since = now - 7 * 24 * 60 * 60_000
  const dispatches = query(
    `SELECT id,account_key,url,platform_post_id
     FROM social_dispatches
     WHERE platform='binance_square' AND status='success'
       AND (metrics_updated_at IS NULL OR (created_at>=${since}
         AND metrics_updated_at < CASE
         WHEN created_at>=${now - 24 * 60 * 60_000} THEN ${now - 10 * 60_000}
         ELSE ${now - 6 * 60 * 60_000} END))
     ORDER BY metrics_updated_at IS NOT NULL,created_at DESC
     LIMIT 120`,
  )
  const accounts = query(
    `SELECT account_key,platform_user_id,follower_updated_at,historical_metrics_updated_at
     FROM social_automation_accounts ORDER BY slot_offset_minutes`,
  )
  const trackedPosts = query(
    `SELECT account_key,url,platform_post_id FROM social_dispatches
     WHERE platform='binance_square' AND status='success'`,
  )
  const metrics = []
  const accountUids = new Map(
    accounts
      .filter((account) => account.platform_user_id)
      .map((account) => [account.account_key, account.platform_user_id]),
  )
  const accountKeys = new Map(Array.from(accountUids, ([key, uid]) => [uid, key]))
  const trackedIds = new Map(accounts.map((account) => [account.account_key, new Set()]))
  for (const post of trackedPosts) {
    const postId = postIdFrom(post.url, post.platform_post_id)
    if (postId) trackedIds.get(post.account_key)?.add(postId)
  }
  const queue = dispatches
    .map((dispatch) => ({ ...dispatch, postId: postIdFrom(dispatch.url, dispatch.platform_post_id) }))
    .filter((dispatch) => dispatch.postId)

  await Promise.all(Array.from({ length: Math.min(6, queue.length) }, async () => {
    for (let dispatch = queue.shift(); dispatch; dispatch = queue.shift()) {
      try {
        const item = postMetrics(await binanceJson(`${DETAIL_ENDPOINT}/${dispatch.postId}`))
        if (!item) throw new Error('帖子指标字段缺失')
        const accountKey = accountKeys.get(item.squareUid) ?? dispatch.account_key
        metrics.push({ dispatchId: dispatch.id, accountKey, ...item })
        if (accountKey !== dispatch.account_key) {
          trackedIds.get(dispatch.account_key)?.delete(item.postId)
          trackedIds.get(accountKey)?.add(item.postId)
        }
      } catch (error) {
        console.error(`帖子 ${dispatch.postId} 同步失败：${error instanceof Error ? error.message : String(error)}`)
      }
    }
  }))

  const history = []
  for (const account of accounts) {
    const squareUid = accountUids.get(account.account_key)
    const stale = !account.historical_metrics_updated_at ||
      now - Number(account.historical_metrics_updated_at) >= 24 * 60 * 60_000
    if (!squareUid || !stale) continue
    try {
      const result = await historicalMetrics(squareUid, trackedIds.get(account.account_key) ?? new Set(), since)
      history.push({ accountKey: account.account_key, ...result })
      console.log(`${account.account_key} 历史阅读同步完成：${result.pages} 页`)
    } catch (error) {
      console.error(`${account.account_key} 历史阅读同步失败：${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const followers = []
  for (const account of accounts) {
    const squareUid = accountUids.get(account.account_key)
    const stale = !account.follower_updated_at || now - Number(account.follower_updated_at) >= 10 * 60_000
    if (!squareUid || !stale) continue
    try {
      const profile = await binanceJson(USER_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ squareUid, getFollowCount: true, queryFollowersInfo: true }),
      })
      const followerCount = count(profile?.totalFollowerCount)
      if (followerCount === null) throw new Error('关注人数缺失')
      followers.push({ accountKey: account.account_key, squareUid, followerCount })
    } catch (error) {
      console.error(`${account.account_key} 关注人数同步失败：${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const statements = [
    ...metrics.map((item) =>
      `UPDATE social_dispatches SET account_key=${quote(item.accountKey)},platform_post_id=${quote(item.postId)},` +
      `view_count=${quote(item.views)},like_count=${quote(item.likes)},` +
      `comment_count=${quote(item.comments)},share_count=${quote(item.shares)},` +
      `metrics_updated_at=${now} WHERE id=${item.dispatchId}`),
    ...followers.map((item) =>
      `UPDATE social_automation_accounts SET platform_user_id=${quote(item.squareUid)},` +
      `follower_count=${item.followerCount},follower_updated_at=${now} ` +
      `WHERE account_key=${quote(item.accountKey)}`),
    ...history.map((item) =>
      `UPDATE social_automation_accounts SET historical_view_count=${item.totalViews},` +
      `historical_views_7d=${item.views7d},historical_metrics_updated_at=${now} ` +
      `WHERE account_key=${quote(item.accountKey)}`),
  ]
  if (statements.length > 0) query(`${statements.join(';')};`)
  console.log(`同步完成：${metrics.length} 条帖子，${followers.length} 个账号关注人数，${history.length} 个账号历史阅读`)
}

if (process.argv.includes('--self-test')) {
  assert.equal(postIdFrom('https://app.binance.com/uni-qr/cpos/359146720776031?r=x'), '359146720776031')
  assert.equal(postIdFrom('https://www.binance.com/en/square/post/123'), '123')
  assert.deepEqual(postMetrics({
    id: 123,
    squareUid: 'uid',
    viewCount: 20,
    likeCount: 2,
    commentCount: 1,
    shareCount: 3,
  }), {
    postId: '123', squareUid: 'uid', views: 20, likes: 2, comments: 1, shares: 3,
  })
  assert.deepEqual(profilePage({
    timeOffset: 456,
    contents: [{ id: 123, createTime: 100, viewCount: 20 }, { id: 124, createTime: 90, viewCount: 0 }],
  }), {
    nextOffset: 456,
    posts: [
      { postId: '123', createdAt: 100, views: 20 },
      { postId: '124', createdAt: 90, views: 0 },
    ],
  })
  console.log('币安广场指标解析自检通过')
} else {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error))
    process.exitCode = 1
  })
}
