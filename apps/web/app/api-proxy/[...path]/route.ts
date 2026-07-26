import { getCloudflareContext } from '@opennextjs/cloudflare'
import type { NextRequest } from 'next/server'

const LEGACY_API_UPSTREAM =
  process.env.LEGACY_API_UPSTREAM_URL ?? 'http://localhost:8000'
const INDEPENDENT_API_ORIGIN = 'https://midas-trading-api.internal'
const INDEPENDENT_API_FALLBACK =
  process.env.API_AUTH_FALLBACK_URL ?? 'http://localhost:8787'

type RouteContext = {
  params: Promise<{ path: string[] }>
}

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params
  const pathname = `/${path.join('/')}`
  const incomingUrl = new URL(request.url)
  const isIndependentApi =
    pathname.startsWith('/api/v1/auth/') ||
    pathname.startsWith('/api/v1/user/') ||
    pathname.startsWith('/api/v1/watchlist') ||
    pathname === '/api/v1/health' ||
    pathname === '/api/v1/ready'
  const upstreamUrl = new URL(
    pathname,
    isIndependentApi ? INDEPENDENT_API_ORIGIN : LEGACY_API_UPSTREAM,
  )
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
  } else {
    response = await fetch(upstreamUrl, init)
  }

  const responseHeaders = new Headers(response.headers)
  responseHeaders.delete('access-control-allow-origin')
  responseHeaders.delete('access-control-allow-credentials')

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
