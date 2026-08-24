import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'

const DATABASE = 'midas-trading-db'
const DETAIL_ENDPOINT =
  'https://www.binance.com/bapi/composite/v3/friendly/pgc/special/content/detail'
const USER_ENDPOINT =
  'https://www.binance.com/bapi/composite/v3/friendly/pgc/user/client'

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

async function main() {
  const now = Date.now()
  const dispatches = query(
    `SELECT id,account_key,url,platform_post_id
     FROM social_dispatches
     WHERE platform='binance_square' AND status='success'
       AND created_at>=${now - 7 * 24 * 60 * 60_000}
       AND (metrics_updated_at IS NULL OR metrics_updated_at < CASE
         WHEN created_at>=${now - 24 * 60 * 60_000} THEN ${now - 10 * 60_000}
         ELSE ${now - 6 * 60 * 60_000} END)
     ORDER BY metrics_updated_at IS NOT NULL,created_at DESC
     LIMIT 120`,
  )
  const accounts = query(
    `SELECT account_key,platform_user_id,follower_updated_at
     FROM social_automation_accounts ORDER BY slot_offset_minutes`,
  )
  const metrics = []
  const accountUids = new Map(
    accounts
      .filter((account) => account.platform_user_id)
      .map((account) => [account.account_key, account.platform_user_id]),
  )
  const queue = dispatches
    .map((dispatch) => ({ ...dispatch, postId: postIdFrom(dispatch.url, dispatch.platform_post_id) }))
    .filter((dispatch) => dispatch.postId)

  await Promise.all(Array.from({ length: Math.min(6, queue.length) }, async () => {
    for (let dispatch = queue.shift(); dispatch; dispatch = queue.shift()) {
      try {
        const item = postMetrics(await binanceJson(`${DETAIL_ENDPOINT}/${dispatch.postId}`))
        if (!item) throw new Error('帖子指标字段缺失')
        metrics.push({ dispatchId: dispatch.id, ...item })
        accountUids.set(dispatch.account_key, item.squareUid)
      } catch (error) {
        console.error(`帖子 ${dispatch.postId} 同步失败：${error instanceof Error ? error.message : String(error)}`)
      }
    }
  }))

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
      `UPDATE social_dispatches SET platform_post_id=${quote(item.postId)},` +
      `view_count=${quote(item.views)},like_count=${quote(item.likes)},` +
      `comment_count=${quote(item.comments)},share_count=${quote(item.shares)},` +
      `metrics_updated_at=${now} WHERE id=${item.dispatchId}`),
    ...followers.map((item) =>
      `UPDATE social_automation_accounts SET platform_user_id=${quote(item.squareUid)},` +
      `follower_count=${item.followerCount},follower_updated_at=${now} ` +
      `WHERE account_key=${quote(item.accountKey)}`),
  ]
  if (statements.length > 0) query(`${statements.join(';')};`)
  console.log(`同步完成：${metrics.length} 条帖子，${followers.length} 个账号关注人数`)
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
  console.log('币安广场指标解析自检通过')
} else {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error))
    process.exitCode = 1
  })
}
