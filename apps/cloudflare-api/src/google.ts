import { createRemoteJWKSet, jwtVerify } from 'jose'

import { HttpError } from './http'

const GOOGLE_JWKS = createRemoteJWKSet(
  new URL('https://www.googleapis.com/oauth2/v3/certs'),
)
const GOOGLE_ISSUERS = [
  'https://accounts.google.com',
  'accounts.google.com',
]

export type GoogleIdentity = Readonly<{
  subject: string
  email: string
  name: string | null
  picture: string | null
}>

export async function verifyGoogleIdToken(
  token: string,
  audience: string,
): Promise<GoogleIdentity> {
  try {
    const { payload } = await jwtVerify(token, GOOGLE_JWKS, {
      algorithms: ['RS256'],
      audience,
      issuer: GOOGLE_ISSUERS,
    })

    if (
      typeof payload.sub !== 'string' ||
      typeof payload.email !== 'string' ||
      payload.email_verified !== true
    ) {
      throw new HttpError(403, 'Google 邮箱未验证或身份信息不完整')
    }

    return {
      subject: payload.sub,
      email: payload.email.trim().toLowerCase(),
      name: typeof payload.name === 'string' ? payload.name : null,
      picture: typeof payload.picture === 'string' ? payload.picture : null,
    }
  } catch (error) {
    if (error instanceof HttpError) throw error
    console.warn(
      JSON.stringify({
        event: 'auth.google.invalid_token',
        error: error instanceof Error ? error.message : String(error),
      }),
    )
    throw new HttpError(401, 'Google 登录凭据无效')
  }
}
