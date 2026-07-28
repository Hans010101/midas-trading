/**
 * Commercial feature switches.
 *
 * Membership implementation is intentionally retained so it can be restored
 * later. While disabled, every authenticated account receives full access.
 */
export const MEMBERSHIP_GATING_ENABLED = false

export function hasFullFeatureAccess(
  isAuthenticated: boolean,
  plan?: string,
): boolean {
  return (
    isAuthenticated &&
    (!MEMBERSHIP_GATING_ENABLED || plan === 'pro' || plan === 'registered')
  )
}
