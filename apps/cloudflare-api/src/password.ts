import { scrypt } from 'node:crypto'

import {
  base64UrlDecode,
  base64UrlEncode,
  hmacSha256,
  randomToken,
} from './crypto'

const SCRYPT_N = 32_768
const SCRYPT_R = 8
const SCRYPT_P = 3
const SCRYPT_MAX_MEMORY = 64 * 1024 * 1024
const HASH_BYTES = 32
const ALGORITHM = 'scrypt'

async function derivePasswordHash(
  password: string,
  pepper: string,
  salt: Uint8Array,
  n: number,
  r: number,
  p: number,
): Promise<Uint8Array> {
  const pepperedPassword = await hmacSha256(pepper, password)
  return new Promise((resolve, reject) => {
    scrypt(
      pepperedPassword,
      salt,
      HASH_BYTES,
      { N: n, r, p, maxmem: SCRYPT_MAX_MEMORY },
      (error, derivedKey) => {
        if (error) {
          reject(error)
          return
        }
        resolve(new Uint8Array(derivedKey))
      },
    )
  })
}

export async function hashPassword(
  password: string,
  pepper: string,
): Promise<string> {
  const salt = base64UrlDecode(randomToken(16))
  const derived = await derivePasswordHash(
    password,
    pepper,
    salt,
    SCRYPT_N,
    SCRYPT_R,
    SCRYPT_P,
  )
  return [
    ALGORITHM,
    String(SCRYPT_N),
    String(SCRYPT_R),
    String(SCRYPT_P),
    base64UrlEncode(salt),
    base64UrlEncode(derived),
  ].join('$')
}

export async function verifyPassword(
  password: string,
  storedHash: string,
  pepper: string,
): Promise<boolean> {
  const [algorithm, nText, rText, pText, saltText, expectedText, extra] =
    storedHash.split('$')
  const n = Number(nText)
  const r = Number(rText)
  const p = Number(pText)
  if (
    algorithm !== ALGORITHM ||
    n !== SCRYPT_N ||
    r !== SCRYPT_R ||
    p !== SCRYPT_P ||
    !saltText ||
    !expectedText ||
    extra !== undefined
  ) {
    return false
  }

  try {
    const salt = base64UrlDecode(saltText)
    const expected = base64UrlDecode(expectedText)
    const actual = await derivePasswordHash(
      password,
      pepper,
      salt,
      n,
      r,
      p,
    )
    if (actual.byteLength !== expected.byteLength) return false
    return crypto.subtle.timingSafeEqual(actual, expected)
  } catch {
    return false
  }
}
