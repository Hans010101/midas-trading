/**
 * Routes owned by the independent midas-trading Cloudflare API.
 *
 * Keep this list explicit while legacy analysis endpoints are still being
 * migrated. In particular, the decision card and structure diagnosis must
 * never be sent to the legacy project API because Cloudflare session tokens
 * are intentionally independent.
 */
export function isIndependentApiPath(pathname: string): boolean {
  return (
    pathname.startsWith('/api/v1/auth/') ||
    pathname.startsWith('/api/v1/user/') ||
    pathname.startsWith('/api/v1/watchlist') ||
    pathname.startsWith('/api/v1/academy/') ||
    pathname.startsWith('/api/v1/quota/') ||
    pathname.startsWith('/api/v1/invite/') ||
    pathname === '/api/v1/redeem' ||
    pathname.startsWith('/api/v1/admin/') ||
    pathname.startsWith('/api/v1/cn/') ||
    pathname.startsWith('/api/v1/us/') ||
    pathname.startsWith('/api/v1/hk/') ||
    pathname.startsWith('/api/v1/crypto/') ||
    pathname.startsWith('/api/v1/econ/') ||
    pathname.startsWith('/api/v1/screener/') ||
    pathname.startsWith('/api/v1/alert-rules') ||
    pathname === '/api/v1/bot-preset' ||
    pathname.startsWith('/api/v1/notifications/') ||
    pathname.startsWith('/api/v1/telegram/') ||
    pathname.startsWith('/api/v1/feishu/') ||
    pathname.startsWith('/api/v1/overview/') ||
    pathname.startsWith('/api/v1/market/') ||
    pathname.startsWith('/api/v1/support/') ||
    pathname.startsWith('/api/v1/track/') ||
    pathname === '/api/v1/analysis/decision-card' ||
    pathname === '/api/v1/analysis/strategy-signals' ||
    pathname === '/api/v1/analysis/strategy-recommend' ||
    pathname === '/api/v1/structure/diagnose' ||
    pathname === '/api/v1/health' ||
    pathname === '/api/v1/ready'
  )
}
