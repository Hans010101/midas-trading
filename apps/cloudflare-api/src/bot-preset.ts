import { authenticate } from './auth'
import {
  HttpError,
  jsonResponse,
  readJsonObject,
} from './http'

const DEFAULT_PRESET = Object.freeze({
  perp_leverage: 3,
  perp_notional_usdt: '100',
  perp_margin_mode: 'isolated',
  spot_notional_cny: '10000',
  spot_notional_usd: '1000',
})

type PresetRow = Readonly<{
  perp_leverage: number
  perp_notional_usdt: string
  perp_margin_mode: string
  spot_notional_cny: string
  spot_notional_usd: string
}>

function positiveDecimal(
  body: Readonly<Record<string, unknown>>,
  key: string,
): string {
  const value = body[key]
  if (
    typeof value !== 'number' ||
    !Number.isFinite(value) ||
    value <= 0 ||
    value > 10_000_000
  ) {
    throw new HttpError(400, `${key} 格式无效`)
  }
  return String(value)
}

async function getPreset(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const auth = await authenticate(request, env)
  const row = await env.DB
    .prepare(
      `SELECT perp_leverage, perp_notional_usdt, perp_margin_mode,
              spot_notional_cny, spot_notional_usd
       FROM bot_order_presets
       WHERE user_id = ?`,
    )
    .bind(auth.user.id)
    .first<PresetRow>()

  return jsonResponse(row ?? DEFAULT_PRESET, 200, requestId, request.method)
}

async function putPreset(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const auth = await authenticate(request, env)
  const body = await readJsonObject(request)
  const leverage = body.perp_leverage
  if (
    typeof leverage !== 'number' ||
    !Number.isInteger(leverage) ||
    leverage < 1 ||
    leverage > 20
  ) {
    throw new HttpError(400, 'perp_leverage 格式无效')
  }
  const marginMode = body.perp_margin_mode ?? 'isolated'
  if (marginMode !== 'isolated' && marginMode !== 'cross') {
    throw new HttpError(400, 'perp_margin_mode 格式无效')
  }

  const values = {
    perpNotionalUsdt: positiveDecimal(body, 'perp_notional_usdt'),
    spotNotionalCny: positiveDecimal(body, 'spot_notional_cny'),
    spotNotionalUsd: positiveDecimal(body, 'spot_notional_usd'),
  }
  const timestamp = Date.now()
  await env.DB
    .prepare(
      `INSERT INTO bot_order_presets
        (user_id, perp_leverage, perp_notional_usdt, perp_margin_mode,
         spot_notional_cny, spot_notional_usd, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(user_id) DO UPDATE SET
         perp_leverage = excluded.perp_leverage,
         perp_notional_usdt = excluded.perp_notional_usdt,
         perp_margin_mode = excluded.perp_margin_mode,
         spot_notional_cny = excluded.spot_notional_cny,
         spot_notional_usd = excluded.spot_notional_usd,
         updated_at = excluded.updated_at`,
    )
    .bind(
      auth.user.id,
      leverage,
      values.perpNotionalUsdt,
      marginMode,
      values.spotNotionalCny,
      values.spotNotionalUsd,
      timestamp,
      timestamp,
    )
    .run()

  return jsonResponse(
    {
      perp_leverage: leverage,
      perp_notional_usdt: values.perpNotionalUsdt,
      perp_margin_mode: marginMode,
      spot_notional_cny: values.spotNotionalCny,
      spot_notional_usd: values.spotNotionalUsd,
    },
    200,
    requestId,
    request.method,
  )
}

export async function handleBotPresetRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  if (new URL(request.url).pathname !== '/api/v1/bot-preset') return null
  if (request.method === 'GET') return getPreset(request, env, requestId)
  if (request.method === 'PUT') return putPreset(request, env, requestId)
  return jsonResponse(
    { detail: 'Method not allowed' },
    405,
    requestId,
    request.method,
  )
}
