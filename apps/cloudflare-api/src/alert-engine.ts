import { fetchMarketKlines, type Kline } from './market'
import { deliverUserNotification } from './notifications'
import { fetchCryptoAiContext, fetchCryptoGlobal, fetchFearGreed } from './crypto-market'
import { analyzeChanItems } from './chan-analysis'

type AlertRule = Readonly<{
  id: number
  user_id: string
  market: string
  symbol: string | null
  indicator: string
  operator: string
  threshold: string
  timeframe: string | null
  cooldown_sec: number
  last_condition_met: number | null
  last_triggered_at: number | null
}>

function mean(values: number[]): number {
  return values.length === 0
    ? 0
    : values.reduce((sum, value) => sum + value, 0) / values.length
}

function ema(values: number[], period: number): number[] {
  if (values.length === 0) return []
  const alpha = 2 / (period + 1)
  const result = [values[0]!]
  for (let index = 1; index < values.length; index += 1) {
    result.push(values[index]! * alpha + result[index - 1]! * (1 - alpha))
  }
  return result
}

function rsi(values: number[], period = 14): number {
  if (values.length <= period) return 50
  let gains = 0
  let losses = 0
  for (let index = values.length - period; index < values.length; index += 1) {
    const change = values[index]! - values[index - 1]!
    if (change >= 0) gains += change
    else losses -= change
  }
  if (losses === 0) return gains > 0 ? 100 : 50
  return 100 - 100 / (1 + gains / losses)
}

function stddev(values: number[]): number {
  const average = mean(values)
  return Math.sqrt(mean(values.map((value) => (value - average) ** 2)))
}

export function technicalIndicator(
  indicator: string,
  items: Kline[],
): number | null {
  const closes = items.map((item) => item.close)
  const latest = items.at(-1)
  if (!latest || closes.length < 2) return null
  switch (indicator) {
    case 'price':
      return latest.close
    case 'price_change_pct':
      return ((latest.close - closes.at(-2)!) / closes.at(-2)!) * 100
    case 'volume':
      return latest.volume
    case 'ma_5':
      return mean(closes.slice(-5))
    case 'ma_20':
      return mean(closes.slice(-20))
    case 'ma_60':
      return mean(closes.slice(-60))
    case 'macd_hist': {
      const fast = ema(closes, 12)
      const slow = ema(closes, 26)
      const macd = closes.map((_, index) => fast[index]! - slow[index]!)
      const signal = ema(macd, 9)
      return macd.at(-1)! - signal.at(-1)!
    }
    case 'rsi_14':
      return rsi(closes)
    case 'boll_pctb': {
      const window = closes.slice(-20)
      const middle = mean(window)
      const deviation = stddev(window)
      return deviation === 0 ? 50 : ((latest.close - (middle - 2 * deviation)) / (4 * deviation)) * 100
    }
    default:
      return null
  }
}

function compare(value: number, operator: string, threshold: number): boolean {
  if (operator === 'gt') return value > threshold
  if (operator === 'gte') return value >= threshold
  if (operator === 'lt') return value < threshold
  return value <= threshold
}

type BoardRow = Readonly<{ symbol: string; sector: string; change_pct: number }>

async function boardRows(
  env: Env,
  market: string,
  cache: Map<string, Promise<BoardRow[]>>,
): Promise<BoardRow[]> {
  let pending = cache.get(market)
  if (!pending) {
    pending = env.DB.prepare(
      'SELECT payload_json FROM market_home_boards WHERE market = ?',
    ).bind(market).first<{ payload_json: string }>().then((row) => {
      if (!row) return []
      const payload = JSON.parse(row.payload_json) as { rows?: BoardRow[] }
      return payload.rows ?? []
    })
    cache.set(market, pending)
  }
  return pending
}

async function structureIndicator(
  env: Env,
  rule: AlertRule,
  cache: Map<string, Promise<BoardRow[]>>,
): Promise<number | null> {
  if (rule.indicator === 'index_change_pct') {
    const row = await env.DB.prepare(
      `SELECT change_pct FROM market_overview_quotes
       WHERE category = 'index' AND market = ? AND symbol = ?`,
    ).bind(rule.market, rule.symbol).first<{ change_pct: number }>()
    return row?.change_pct ?? null
  }
  const rows = await boardRows(env, rule.market, cache)
  if (rule.indicator === 'sector_change_pct') {
    const selected = rows.filter((row) => row.sector === rule.symbol)
    return selected.length
      ? mean(selected.map((row) => row.change_pct))
      : null
  }
  const advancing = rows.filter((row) => row.change_pct > 0.01).length
  const declining = rows.filter((row) => row.change_pct < -0.01).length
  return advancing + declining > 0 ? advancing / (advancing + declining) * 100 : null
}

export async function runAlertScan(env: Env): Promise<void> {
  const rows = await env.DB
    .prepare(
      `SELECT r.id, r.user_id, r.market, r.symbol, r.indicator, r.operator,
              r.threshold, r.timeframe, r.cooldown_sec,
              s.last_condition_met, s.last_triggered_at
       FROM alert_rules r
       LEFT JOIN alert_rule_states s ON s.rule_id = r.id
       WHERE r.enabled = 1
       ORDER BY r.id
       LIMIT 100`,
    )
    .all<AlertRule>()
  const cache = new Map<string, Promise<Kline[]>>()
  const derivativeCache = new Map<string, ReturnType<typeof fetchCryptoAiContext>>()
  const boardCache = new Map<string, Promise<BoardRow[]>>()
  let globalPromise: ReturnType<typeof fetchCryptoGlobal> | undefined
  let fearGreedPromise: ReturnType<typeof fetchFearGreed> | undefined
  const now = Date.now()
  for (const rule of rows.results) {
    let value: number | null = null
    let error: string | null = null
    try {
      if (rule.indicator === 'fear_greed') {
        fearGreedPromise ??= fetchFearGreed()
        value = (await fearGreedPromise).value
      } else if (rule.indicator === 'btc_dominance') {
        globalPromise ??= fetchCryptoGlobal()
        value = (await globalPromise).btc_dominance
      } else if (['cn_breadth_up_ratio', 'hk_breadth_up_ratio', 'sector_change_pct', 'index_change_pct'].includes(rule.indicator)) {
        value = await structureIndicator(env, rule, boardCache)
      } else if (['funding_rate', 'open_interest_usd', 'long_short_ratio', 'basis_pct'].includes(rule.indicator)) {
        if (!rule.symbol) throw new Error('该规则需要指定标的')
        let pending = derivativeCache.get(rule.symbol)
        if (!pending) {
          pending = fetchCryptoAiContext(rule.symbol)
          derivativeCache.set(rule.symbol, pending)
        }
        const metrics = await pending
        value = rule.indicator === 'funding_rate'
          ? (metrics.funding_rate === null ? null : metrics.funding_rate * 100)
          : rule.indicator === 'open_interest_usd'
            ? metrics.open_interest_usd
            : rule.indicator === 'long_short_ratio'
              ? metrics.account_long_short_ratio
              : metrics.basis_pct
      } else {
        if (!rule.symbol) throw new Error('该规则需要指定标的')
        const period = rule.timeframe ?? '1h'
        const key = `${rule.market}|${rule.symbol}|${period}`
        let pending = cache.get(key)
        if (!pending) {
          pending = fetchMarketKlines({
            symbol: rule.symbol,
            market: rule.market,
            period,
            instrument: rule.market === 'crypto' ? 'perp' : 'spot',
            limit: 80,
          }).then((result) => result.items)
          cache.set(key, pending)
        }
        const items = await pending
        if (rule.indicator === 'chan_buy' || rule.indicator === 'chan_sell') {
          const latest = analyzeChanItems(items).buy_sell_points.at(-1)?.kind
          value = latest?.startsWith(rule.indicator === 'chan_buy' ? 'B' : 'S') ? 1 : 0
        } else value = technicalIndicator(rule.indicator, items)
      }
      if (value === null) throw new Error(`指标 ${rule.indicator} 暂无可计算数据`)
      const condition = compare(value, rule.operator, Number(rule.threshold))
      const cooldownPassed =
        !rule.last_triggered_at || now - rule.last_triggered_at >= rule.cooldown_sec * 1_000
      const shouldTrigger = condition && rule.last_condition_met !== 1 && cooldownPassed
      if (shouldTrigger) {
        const operatorText = { gt: '>', gte: '≥', lt: '<', lte: '≤' }[rule.operator] ?? rule.operator
        await deliverUserNotification(env, {
          userId: rule.user_id,
          category: 'price_alert',
          title: `${rule.symbol ?? rule.market.toUpperCase()} 提醒已触发`,
          body: `${rule.indicator} 当前值 ${value.toFixed(6)} ${operatorText} ${rule.threshold}`,
          dedupeKey: `alert:${rule.id}:${Math.floor(now / (rule.cooldown_sec * 1_000))}`,
        })
      }
      await env.DB
        .prepare(
          `INSERT INTO alert_rule_states
            (rule_id, last_value, last_condition_met, last_evaluated_at,
             last_triggered_at, consecutive_failures, last_error, updated_at)
           VALUES (?, ?, ?, ?, ?, 0, NULL, ?)
           ON CONFLICT(rule_id) DO UPDATE SET
             last_value = excluded.last_value,
             last_condition_met = excluded.last_condition_met,
             last_evaluated_at = excluded.last_evaluated_at,
             last_triggered_at = COALESCE(excluded.last_triggered_at, alert_rule_states.last_triggered_at),
             consecutive_failures = 0,
             last_error = NULL,
             updated_at = excluded.updated_at`,
        )
        .bind(rule.id, value, condition ? 1 : 0, now, shouldTrigger ? now : null, now)
        .run()
    } catch (cause) {
      error = cause instanceof Error ? cause.message : String(cause)
      await env.DB
        .prepare(
          `INSERT INTO alert_rule_states
            (rule_id, last_evaluated_at, consecutive_failures, last_error, updated_at)
           VALUES (?, ?, 1, ?, ?)
           ON CONFLICT(rule_id) DO UPDATE SET
             last_evaluated_at = excluded.last_evaluated_at,
             consecutive_failures = alert_rule_states.consecutive_failures + 1,
             last_error = excluded.last_error,
             updated_at = excluded.updated_at`,
        )
        .bind(rule.id, now, error, now)
        .run()
    }
  }
}
