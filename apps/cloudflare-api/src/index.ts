import { handleAccountRoute } from './account'
import { handleAdminAnalyticsRoute } from './admin-analytics'
import {
  handleAdminOperationsRoute,
  isAutoPublishTimestamp,
  runAdminOperationsCron,
} from './admin-operations'
import {
  handleAdminTradingRoute,
  runVirtualTradingCron,
} from './admin-trading'
import { handleAdminRoute } from './admin'
import { handleAdminReportsRoute } from './admin-reports'
import { handleAdminMigrationRoute } from './admin-migration'
import { handleAnalysisRoute } from './analysis'
import { runAlertScan } from './alert-engine'
import { handleAcademyRoute } from './academy'
import { handleAlertRulesRoute } from './alert-rules'
import { handleAuthRoute } from './auth'
import { handleBacktestRoute } from './backtest'
import { handleBotPresetRoute } from './bot-preset'
import { handleCryptoMarketRoute } from './crypto-market'
import { handleEconRoute, refreshEconCalendar } from './econ'
import { handleChanAnalysisRoute } from './chan-analysis'
import {
  handleConditionalOrderRoute,
  runConditionalOrderScan,
} from './conditional-orders'
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
import {
  handleVirtualTradingRoute,
  runVirtualFundingSettlement,
  runVirtualRiskScan,
} from './virtual-trading'

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
        (await handleAdminAnalyticsRoute(request, env, requestId)) ??
        (await handleAdminOperationsRoute(request, env, requestId)) ??
        (await handleAdminTradingRoute(request, env, requestId)) ??
        (await handleAdminMigrationRoute(request, env, requestId)) ??
        (await handleAdminReportsRoute(request, env, requestId)) ??
        (await handleAdminRoute(request, env, requestId)) ??
        (await handleBacktestRoute(request, env, requestId)) ??
        (await handleChanAnalysisRoute(request, requestId)) ??
        (await handleAnalysisRoute(request, env, requestId)) ??
        (await handleBotPresetRoute(request, env, requestId)) ??
        (await handleAccountRoute(request, env, requestId)) ??
        (await handleConditionalOrderRoute(request, env, requestId)) ??
        (await handleVirtualTradingRoute(request, env, requestId)) ??
        (await handleAlertRulesRoute(request, env, requestId)) ??
        (await handleNotificationRoute(request, env, requestId)) ??
        (await handleProfileRoute(request, env, requestId)) ??
        (await handleWatchlistRoute(request, env, requestId)) ??
        (await handleRedeemRoute(request, env, requestId)) ??
        (await handleAcademyRoute(request, env, requestId)) ??
        (await handleCryptoMarketRoute(request, requestId)) ??
        (await handleEconRoute(request, env, requestId)) ??
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
    const socialPublishSlot = isAutoPublishTimestamp(controller.scheduledTime)
    const tasks: Array<{ name: string; promise: Promise<void> }> = socialPublishSlot
      ? [{
          name: 'admin_operations',
          promise: runAdminOperationsCron(env, controller.scheduledTime),
        }]
      : [
          {
            name: 'market_refresh',
            promise: minute % 10 === 5
              ? refreshMarketBoards(env)
              : refreshGlobalOverview(env).then(() => undefined),
          },
          { name: 'virtual_trading', promise: runVirtualTradingCron(env) },
          { name: 'user_virtual_risk', promise: runVirtualRiskScan(env) },
          {
            name: 'user_virtual_funding',
            promise: runVirtualFundingSettlement(env, controller.scheduledTime),
          },
          { name: 'conditional_orders', promise: runConditionalOrderScan(env) },
          { name: 'alert_scan', promise: runAlertScan(env) },
          ...(minute === 15
            ? [{ name: 'econ_calendar', promise: refreshEconCalendar(env).then(() => undefined) }]
            : []),
          {
            name: 'admin_operations',
            promise: runAdminOperationsCron(env, controller.scheduledTime),
          },
        ]
    ctx.waitUntil(
      Promise.allSettled(tasks.map((task) => task.promise)).then((results) => {
        results.forEach((result, index) => {
          if (result.status === 'rejected') {
            console.error(JSON.stringify({
              event: 'scheduled.task_failed',
              task: tasks[index]?.name ?? 'unknown',
              error:
                result.reason instanceof Error
                  ? result.reason.message
                  : String(result.reason),
            }))
          }
        })
      }),
    )
  },
} satisfies ExportedHandler<Env>
