import 'server-only'

import { getCloudflareContext } from '@opennextjs/cloudflare'

const INTERNAL_ORIGIN = 'https://midas-trading-api.internal'
const LOCAL_FALLBACK =
  process.env.API_AUTH_FALLBACK_URL ?? 'http://localhost:8787'

/**
 * Server-side calls to the independent Midas Trading API.
 *
 * Production uses a Cloudflare Service Binding so auth traffic never leaves
 * Cloudflare or falls back to the legacy project API. The URL fallback exists
 * only for `next dev`, where Cloudflare bindings are not always available.
 */
export async function midasTradingApiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  try {
    const { env } = getCloudflareContext()
    if (env.MIDAS_TRADING_API) {
      return env.MIDAS_TRADING_API.fetch(
        new Request(new URL(path, INTERNAL_ORIGIN), init),
      )
    }
  } catch {
    // `next dev` without the OpenNext Cloudflare runtime: use local Worker.
  }

  return fetch(new URL(path, LOCAL_FALLBACK), init)
}
