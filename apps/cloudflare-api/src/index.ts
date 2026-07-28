import { handleAccountRoute } from './account'
import { handleAnalysisRoute } from './analysis'
import { handleAcademyRoute } from './academy'
import { handleAlertRulesRoute } from './alert-rules'
import { handleAuthRoute } from './auth'
import { handleBotPresetRoute } from './bot-preset'
import { handleCryptoMarketRoute } from './crypto-market'
import { handleEconRoute } from './econ'
import { HttpError, jsonResponse } from './http'
import { handleMarketRoute } from './market'
import { handleNotificationRoute } from './notifications'
import {
  handleMarketHomeRoute,
  refreshMarketBoards,
} from './market-home'
import { handleOverviewRoute, refreshGlobalOverview } from './overview'
import { handleProfileRoute } from './profile'
import { handleRedeemRoute } from './redeem'
import { handleScreenerRoute } from './screener'
import { handleSupportRoute } from './support'
import { handleWatchlistRoute } from './watchlist'

async function databaseReady(db: D1Database): Promise<boolean> {
  const row = await db.prepare('SELECT 1 AS ok').first<{ ok: number }>()
  return row?.ok === 1
}

export async function routeRequest(
  request: Request,
  config: Readonly<{
    environment: string
    projectName: string
    apiVersion: string
  }>,
  requestId: string,
  now: string,
  db?: D1Database,
): Promise<Response> {
  const url = new URL(request.url)

  if (url.pathname === '/' && (request.method === 'GET' || request.method === 'HEAD')) {
    return jsonResponse(
      {
        name: `${config.projectName}-api`,
        version: config.apiVersion,
        runtime: 'cloudflare-workers',
      },
      200,
      requestId,
      request.method,
    )
  }

  if (
    (url.pathname === '/health' || url.pathname === '/api/v1/health') &&
    (request.method === 'GET' || request.method === 'HEAD')
  ) {
    return jsonResponse(
      {
        status: 'ok',
        project: config.projectName,
        environment: config.environment,
        runtime: 'cloudflare-workers',
        independent: true,
        timestamp: now,
      },
      200,
      requestId,
      request.method,
    )
  }

  if (
    (url.pathname === '/ready' || url.pathname === '/api/v1/ready') &&
    (request.method === 'GET' || request.method === 'HEAD')
  ) {
    const ready = db ? await databaseReady(db) : false
    return jsonResponse(
      {
        status: ready ? 'ok' : 'unavailable',
        database: ready ? 'ok' : 'unavailable',
      },
      ready ? 200 : 503,
      requestId,
      request.method,
    )
  }

  if (url.pathname === '/health' || url.pathname === '/api/v1/health') {
    return jsonResponse(
      {
        error: {
          code: 'method_not_allowed',
          message: 'Method not allowed',
        },
      },
      405,
      requestId,
      request.method,
    )
  }

  return jsonResponse(
    {
      error: {
        code: 'not_found',
        message: 'Route not found',
      },
    },
    404,
    requestId,
    request.method,
  )
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const requestId = request.headers.get('cf-ray') ?? crypto.randomUUID()
    const startedAt = Date.now()

    try {
      const response =
        (await handleAuthRoute(request, env, requestId)) ??
        (await handleAnalysisRoute(request, env, requestId)) ??
        (await handleBotPresetRoute(request, env, requestId)) ??
        (await handleAccountRoute(request, env, requestId)) ??
        (await handleAlertRulesRoute(request, env, requestId)) ??
        (await handleNotificationRoute(request, env, requestId)) ??
        (await handleProfileRoute(request, env, requestId)) ??
        (await handleWatchlistRoute(request, env, requestId)) ??
        (await handleRedeemRoute(request, env, requestId)) ??
        (await handleAcademyRoute(request, env, requestId)) ??
        (await handleCryptoMarketRoute(request, requestId)) ??
        (await handleEconRoute(request, requestId)) ??
        (await handleOverviewRoute(request, env, requestId)) ??
        (await handleMarketHomeRoute(request, env, requestId)) ??
        (await handleMarketRoute(request, env, requestId)) ??
        (await handleScreenerRoute(request, env, requestId)) ??
        (await handleSupportRoute(request, env, requestId)) ??
        (await routeRequest(
          request,
          {
            environment: env.ENVIRONMENT,
            projectName: env.PROJECT_NAME,
            apiVersion: env.API_VERSION,
          },
          requestId,
          new Date().toISOString(),
          env.DB,
        ))

      console.log(
        JSON.stringify({
          event: 'request.complete',
          requestId,
          method: request.method,
          path: new URL(request.url).pathname,
          status: response.status,
          durationMs: Date.now() - startedAt,
        }),
      )
      return response
    } catch (error) {
      console.error(
        JSON.stringify({
          event: 'request.failed',
          requestId,
          method: request.method,
          path: new URL(request.url).pathname,
          error: error instanceof Error ? error.message : String(error),
        }),
      )
      if (error instanceof HttpError) {
        return jsonResponse(
          { detail: error.detail },
          error.status,
          requestId,
          request.method,
        )
      }
      return jsonResponse(
        {
          error: {
            code: 'internal_error',
            message: 'Internal server error',
          },
        },
        500,
        requestId,
        request.method,
      )
    }
  },
  async scheduled(
    controller: ScheduledController,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    const minute = new Date(controller.scheduledTime).getUTCMinutes()
    ctx.waitUntil(
      minute % 10 === 5
        ? refreshMarketBoards(env)
        : refreshGlobalOverview(env).then(() => undefined),
    )
  },
} satisfies ExportedHandler<Env>
