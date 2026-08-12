/**
 * Every v1 route is owned by the independent midas-trading Cloudflare API.
 * Unknown or retired routes must fail closed at the new Worker; they must
 * never leak Cloudflare session tokens or data into the legacy project.
 */
export function isIndependentApiPath(pathname: string): boolean {
  return pathname === '/health' || pathname === '/ready' || pathname.startsWith('/api/v1/')
}
