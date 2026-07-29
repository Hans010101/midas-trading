const LOCKED_ADMIN_GMAIL_LOCAL = 'hanspan007'

function canonicalGmail(email: string): string | null {
  const normalized = email.trim().toLowerCase()
  const at = normalized.lastIndexOf('@')
  if (at <= 0) return null
  const local = normalized.slice(0, at).replaceAll('.', '')
  const domain = normalized.slice(at + 1)
  if (domain !== 'gmail.com' && domain !== 'googlemail.com') return null
  return local ? `${local}@gmail.com` : null
}

/**
 * The owner supplied hans.pan.007@gmail.com. Gmail dot aliases resolve to the
 * same mailbox, while the existing production row is hans.pan007@gmail.com.
 */
export function isLockedAdminEmail(email: string): boolean {
  return canonicalGmail(email) === `${LOCKED_ADMIN_GMAIL_LOCAL}@gmail.com`
}

export function roleForEmail(email: string): 'admin' | 'user' {
  return isLockedAdminEmail(email) ? 'admin' : 'user'
}
