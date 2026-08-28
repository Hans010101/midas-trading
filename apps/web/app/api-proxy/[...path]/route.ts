import { getCloudflareContext } from '@opennextjs/cloudflare'
import type { NextRequest } from 'next/server'

import { isIndependentApiPath } from '@/lib/server/api-route-policy'

const INDEPENDENT_API_ORIGIN = 'https://midas-trading-api.internal'
const INDEPENDENT_API_FALLBACK =
  process.env.API_AUTH_FALLBACK_URL ?? 'http://localhost:8787'

type RouteContext = {
  params: Promise<{ path: string[] }>
}

async function proxy(request: NextRequest, context: RouteContext) {
  const startedAt = performance.now()
  const { path } = await context.params
  const pathname = `/${path.join('/')}`
  const incomingUrl = new URL(request.url)
  const isIndependentApi = isIndependentApiPath(pathname)
  const upstreamUrl = new URL(pathname, INDEPENDENT_API_ORIGIN)
  upstreamUrl.search = incomingUrl.search

  const headers = new Headers(request.headers)
  headers.delete('host')
  headers.delete('origin')
  headers.delete('referer')
  headers.set('x-public-web-url', incomingUrl.origin)

  let response: Response
  const init: RequestInit = {
    method: request.method,
    headers,
    body:
      request.method === 'GET' || request.method === 'HEAD'
        ? undefined
        : request.body,
    redirect: 'manual',
  }
  if (isIndependentApi) {
    try {
      const { env } = getCloudflareContext()
      response = await env.MIDAS_TRADING_API.fetch(
        new Request(upstreamUrl, init),
      )
    } catch {
      const fallbackUrl = new URL(pathname, INDEPENDENT_API_FALLBACK)
      fallbackUrl.search = incomingUrl.search
      response = await fetch(fallbackUrl, init)
    }
  } else return new Response('Not found', { status: 404 })

  const responseHeaders = new Headers(response.headers)
  responseHeaders.delete('access-control-allow-origin')
  responseHeaders.delete('access-control-allow-credentials')
  responseHeaders.set('server-timing', `midas-api;dur=${(performance.now() - startedAt).toFixed(1)}`)

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  })
}

export const dynamic = 'force-dynamic'

export const GET = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
export const OPTIONS = proxy
export const HEAD = proxy
