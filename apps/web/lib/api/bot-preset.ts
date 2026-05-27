/**
 * Bot 下单后台预设 API client · 0026 G5。
 * GET 无行 → 默认值(与 G4 常量一致)· PUT upsert(本期固定逐仓)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface BotPreset {
  perp_leverage: number
  perp_notional_usdt: string // Decimal → JSON string
  perp_margin_mode: string
  spot_notional_cny: string
  spot_notional_usd: string
}

export interface BotPresetUpdate {
  perp_leverage: number
  perp_notional_usdt: number
  spot_notional_cny: number
  spot_notional_usd: number
}

export class BotPresetApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`BotPresetApi ${status}: ${detail}`)
    this.name = 'BotPresetApiError'
  }
}

async function readDetail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : `HTTP ${resp.status}`
  } catch {
    return `HTTP ${resp.status}`
  }
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

export async function fetchBotPreset(token: string, signal?: AbortSignal): Promise<BotPreset> {
  const r = await fetch(`${API_BASE}/api/v1/bot-preset`, { headers: authHeaders(token), signal })
  if (!r.ok) throw new BotPresetApiError(r.status, await readDetail(r))
  return (await r.json()) as BotPreset
}

export async function updateBotPreset(token: string, payload: BotPresetUpdate): Promise<BotPreset> {
  const r = await fetch(`${API_BASE}/api/v1/bot-preset`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new BotPresetApiError(r.status, await readDetail(r))
  return (await r.json()) as BotPreset
}
