import { execFileSync } from 'node:child_process'

const DATABASE = 'midas-trading-db'
const CONTENT_ENDPOINT =
  'https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add'

function quote(value) {
  if (value === null || value === undefined) return 'NULL'
  if (typeof value === 'number') return String(value)
  return `'${String(value).replaceAll("'", "''")}'`
}

function query(sql) {
  const output = execFileSync(
    'pnpm',
    [
      '--filter',
      '@midas-trading/cloudflare-api',
      'exec',
      'wrangler',
      'd1',
      'execute',
      DATABASE,
      '--remote',
      '--json',
      '--command',
      sql,
    ],
    { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 },
  )
  const start = output.indexOf('[')
  const end = output.lastIndexOf(']')
  if (start < 0 || end < start) throw new Error('D1 未返回 JSON 结果')
  const batches = JSON.parse(output.slice(start, end + 1))
  return batches.flatMap((batch) => batch.results ?? [])
}

function cstMinute() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date())
  const value = (type) =>
    Number(parts.find((part) => part.type === type)?.value ?? 0)
  return value('hour') * 60 + value('minute')
}

function failDispatch(dispatchId, message) {
  const now = Date.now()
  query(
    `UPDATE social_dispatches
     SET status='failed',error=${quote(message.slice(0, 500))},updated_at=${now}
     WHERE id=${dispatchId};
     UPDATE social_automation_config
     SET last_error=${quote(message.slice(0, 500))},updated_at=${now}
     WHERE id=1;`,
  )
}

async function main() {
  const apiKey = process.env.BINANCE_SQUARE_API_KEY?.trim()
  if (!apiKey) throw new Error('BINANCE_SQUARE_API_KEY 未配置')
  const minute = cstMinute()
  if (minute < 8 * 60 || minute > 22 * 60) {
    console.log('当前不在 08:00–22:00 发布窗口，跳过')
    return
  }

  const config = query(
    `SELECT enabled,circuit_open,binance_checked,daily_limit
     FROM social_automation_config WHERE id=1`,
  )[0]
  if (
    !config || config.enabled !== 1 || config.circuit_open === 1 ||
    config.binance_checked !== 1
  ) {
    console.log('自动托管未开启，跳过')
    return
  }

  const used = query(
    `SELECT COUNT(*) AS count FROM social_dispatches
     WHERE source='auto' AND platform='binance_square' AND status='success'
       AND date(updated_at/1000,'unixepoch','+8 hours')=date('now','+8 hours')`,
  )[0]
  if (Number(used?.count ?? 0) >= Number(config.daily_limit)) {
    console.log(`今日已达到 ${config.daily_limit} 条上限，跳过`)
    return
  }

  const now = Date.now()
  const candidate = query(
    `SELECT d.id,d.symbol,d.tweet_text,sd.id AS dispatch_id
     FROM social_drafts d
     LEFT JOIN social_dispatches sd
       ON sd.draft_id=d.id AND sd.platform='binance_square'
     WHERE d.auto_drafted=1 AND d.gen_style='default'
       AND d.compliance_passed=1 AND d.created_at>=${now - 4 * 60 * 60_000}
       AND NOT EXISTS (
         SELECT 1 FROM social_dispatches ok
         WHERE ok.draft_id=d.id AND ok.platform='binance_square'
           AND ok.status='success'
       )
       AND NOT EXISTS (
         SELECT 1 FROM social_drafts recent_d
         JOIN social_dispatches recent_sd ON recent_sd.draft_id=recent_d.id
         WHERE recent_d.symbol=d.symbol
           AND recent_sd.platform='binance_square'
           AND recent_sd.status='success'
           AND recent_sd.updated_at>=${now - 2 * 60 * 60_000}
       )
     ORDER BY d.created_at
     LIMIT 1`,
  )[0]
  if (!candidate) {
    console.log('暂无待发布合规草稿，等待下一轮')
    return
  }

  query(
    `INSERT INTO social_dispatches
       (draft_id,platform,status,url,error,source,created_at,updated_at)
     VALUES (${candidate.id},'binance_square','pending',NULL,NULL,'auto',${now},${now})
     ON CONFLICT(draft_id,platform) DO UPDATE SET
       status='pending',url=NULL,error=NULL,source='auto',updated_at=${now};`,
  )
  const dispatch = query(
    `SELECT id FROM social_dispatches
     WHERE draft_id=${candidate.id} AND platform='binance_square'`,
  )[0]
  if (!dispatch) throw new Error('发布台账认领失败')

  let response
  try {
    response = await fetch(CONTENT_ENDPOINT, {
      method: 'POST',
      headers: {
        'X-Square-OpenAPI-Key': apiKey,
        'Content-Type': 'application/json',
        clienttype: 'binanceSkill',
      },
      body: JSON.stringify({
        contentType: 1,
        bodyTextOnly: [...candidate.tweet_text.trim()].slice(0, 4_000).join(''),
      }),
      signal: AbortSignal.timeout(30_000),
    })
  } catch (error) {
    const message = `币安广场网络错误：${error instanceof Error ? error.message : String(error)}`
    failDispatch(dispatch.id, message)
    throw new Error(message)
  }

  let url = null
  if (response.status !== 504) {
    const raw = await response.text()
    let body
    try {
      body = JSON.parse(raw)
    } catch {
      const message = `币安广场返回非 JSON 响应（HTTP ${response.status}）`
      failDispatch(dispatch.id, message)
      throw new Error(message)
    }
    if (!response.ok || body.code !== '000000') {
      const message = `币安广场拒绝 [${body.code ?? response.status}] ${body.message ?? '未知错误'}`
      failDispatch(dispatch.id, message)
      throw new Error(message)
    }
    url = body.data?.shareLink ?? (
      body.data?.id ? `https://www.binance.com/square/post/${body.data.id}` : null
    )
  }

  const completedAt = Date.now()
  query(
    `UPDATE social_dispatches
     SET status='success',url=${quote(url)},error=NULL,source='auto',updated_at=${completedAt}
     WHERE id=${dispatch.id};
     UPDATE social_drafts SET status='published' WHERE id=${candidate.id};
     UPDATE social_auto_runs
     SET status='success',dispatch_id=${dispatch.id},error=NULL,updated_at=${completedAt}
     WHERE draft_id=${candidate.id};
     UPDATE social_automation_config
     SET failure_count=0,last_error=NULL,updated_at=${completedAt}
     WHERE id=1;`,
  )
  console.log(`发布成功：draft=${candidate.id}${url ? ` ${url}` : ''}`)
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error))
  process.exitCode = 1
})
