const TRIAL_DAYS = 7
export const INVITE_DAYS = 15
const INVITE_CAP_DAYS = 90
const DAY_MS = 24 * 60 * 60 * 1_000
const CODE_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

export function normalizeReferralCode(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const code = value.trim().toUpperCase()
  return /^[0-9A-HJKMNP-TV-Z]{8}$/u.test(code) ? code : null
}

export function attributeInviteStatement(
  db: D1Database,
  inviteeId: string,
  rawCode: unknown,
  timestamp: number,
): D1PreparedStatement | null {
  const code = normalizeReferralCode(rawCode)
  if (!code) return null
  return db
    .prepare(
      `INSERT OR IGNORE INTO invitations
        (id, inviter_id, invitee_id, code, created_at)
       SELECT ?, id, ?, ?, ?
       FROM users
       WHERE invite_code = ? AND id <> ?`,
    )
    .bind(
      crypto.randomUUID(),
      inviteeId,
      code,
      timestamp,
      code,
      inviteeId,
    )
}

function grantTrialStatement(
  db: D1Database,
  userId: string,
  timestamp: number,
): D1PreparedStatement {
  return db
    .prepare(
      `UPDATE users
       SET trial_granted_at = ?,
           subscription_expires_at =
             CASE
               WHEN subscription_expires_at IS NULL
                 OR subscription_expires_at < ?
               THEN ?
               ELSE subscription_expires_at + ?
             END,
           updated_at = ?
       WHERE id = ? AND trial_granted_at IS NULL`,
    )
    .bind(
      timestamp,
      timestamp,
      timestamp + TRIAL_DAYS * DAY_MS,
      TRIAL_DAYS * DAY_MS,
      timestamp,
      userId,
    )
}

function rewardSubscriptionStatement(
  db: D1Database,
  values: Readonly<{
    userId: string
    claimId: string
    timestamp: number
  }>,
): D1PreparedStatement {
  const rewardMs = INVITE_DAYS * DAY_MS
  const capAt = values.timestamp + INVITE_CAP_DAYS * DAY_MS
  return db
    .prepare(
      `UPDATE users
       SET subscription_expires_at =
             MIN(
               CASE
                 WHEN subscription_expires_at IS NULL
                   OR subscription_expires_at < ?
                 THEN ?
                 ELSE subscription_expires_at + ?
               END,
               ?
             ),
           updated_at = ?
       WHERE id = ?
         AND EXISTS (
           SELECT 1
           FROM invitations
           WHERE reward_claim_id = ?
         )`,
    )
    .bind(
      values.timestamp,
      values.timestamp + rewardMs,
      rewardMs,
      capAt,
      values.timestamp,
      values.userId,
      values.claimId,
    )
}

export async function activateVerifiedGrowth(
  db: D1Database,
  userId: string,
  timestamp: number,
): Promise<{
  trialGranted: boolean
  inviteRewarded: boolean
}> {
  const invitation = await db
    .prepare(
      `SELECT id, inviter_id
       FROM invitations
       WHERE invitee_id = ? AND rewarded_at IS NULL`,
    )
    .bind(userId)
    .first<{ id: string; inviter_id: string }>()

  if (!invitation) {
    const trial = await grantTrialStatement(db, userId, timestamp).run()
    return {
      trialGranted: trial.meta.changes === 1,
      inviteRewarded: false,
    }
  }

  const claimId = crypto.randomUUID()
  const results = await db.batch([
    grantTrialStatement(db, userId, timestamp),
    db
      .prepare(
        `UPDATE invitations
         SET rewarded_at = ?, reward_claim_id = ?
         WHERE id = ? AND rewarded_at IS NULL`,
      )
      .bind(timestamp, claimId, invitation.id),
    rewardSubscriptionStatement(db, {
      userId,
      claimId,
      timestamp,
    }),
    rewardSubscriptionStatement(db, {
      userId: invitation.inviter_id,
      claimId,
      timestamp,
    }),
  ])
  return {
    trialGranted: results[0]?.meta.changes === 1,
    inviteRewarded: results[1]?.meta.changes === 1,
  }
}

function generateInviteCode(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8))
  return Array.from(bytes, (byte) => CODE_ALPHABET[byte & 31]).join('')
}

export async function getOrCreateInviteCode(
  db: D1Database,
  userId: string,
): Promise<string> {
  const existing = await db
    .prepare('SELECT invite_code FROM users WHERE id = ?')
    .bind(userId)
    .first<{ invite_code: string | null }>()
  if (!existing) throw new Error('user not found while creating invite code')
  if (existing.invite_code) return existing.invite_code

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const code = generateInviteCode()
    try {
      const updated = await db
        .prepare(
          `UPDATE users
           SET invite_code = ?, updated_at = ?
           WHERE id = ? AND invite_code IS NULL`,
        )
        .bind(code, Date.now(), userId)
        .run()
      if (updated.meta.changes === 1) return code
      const wonByOtherRequest = await db
        .prepare('SELECT invite_code FROM users WHERE id = ?')
        .bind(userId)
        .first<{ invite_code: string | null }>()
      if (wonByOtherRequest?.invite_code) {
        return wonByOtherRequest.invite_code
      }
    } catch (error) {
      if (
        !(error instanceof Error) ||
        !error.message.includes('UNIQUE constraint failed')
      ) {
        throw error
      }
    }
  }
  throw new Error('invite code collision retry exhausted')
}
