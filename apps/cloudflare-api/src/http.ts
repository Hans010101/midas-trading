const MAX_JSON_BODY_BYTES = 16 * 1024

export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail)
    this.name = 'HttpError'
  }
}

const SECURITY_HEADERS = Object.freeze({
  'cache-control': 'no-store',
  'content-type': 'application/json; charset=utf-8',
  'referrer-policy': 'no-referrer',
  'x-content-type-options': 'nosniff',
})

export function jsonResponse(
  body: unknown,
  status: number,
  requestId: string,
  method = 'GET',
): Response {
  const headers = new Headers(SECURITY_HEADERS)
  headers.set('x-request-id', requestId)
  return new Response(method === 'HEAD' ? null : JSON.stringify(body), {
    status,
    headers,
  })
}

export async function readJsonObject(
  request: Request,
): Promise<Record<string, unknown>> {
  if (!request.body) {
    throw new HttpError(400, '请求体不能为空')
  }

  const reader = request.body.getReader()
  const chunks: Uint8Array[] = []
  let totalBytes = 0

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    totalBytes += value.byteLength
    if (totalBytes > MAX_JSON_BODY_BYTES) {
      await reader.cancel()
      throw new HttpError(413, '请求体过大')
    }
    chunks.push(value)
  }

  const body = new Uint8Array(totalBytes)
  let offset = 0
  for (const chunk of chunks) {
    body.set(chunk, offset)
    offset += chunk.byteLength
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(new TextDecoder().decode(body))
  } catch {
    throw new HttpError(400, '请求体不是有效 JSON')
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new HttpError(400, '请求体必须是 JSON 对象')
  }
  return parsed as Record<string, unknown>
}

export function requireString(
  body: Readonly<Record<string, unknown>>,
  key: string,
  options: Readonly<{ min: number; max: number }>,
): string {
  const value = body[key]
  if (
    typeof value !== 'string' ||
    value.length < options.min ||
    value.length > options.max
  ) {
    throw new HttpError(400, `${key} 格式无效`)
  }
  return value
}

export function optionalString(
  body: Readonly<Record<string, unknown>>,
  key: string,
  max: number,
): string | null {
  const value = body[key]
  if (value === undefined || value === null || value === '') return null
  if (typeof value !== 'string' || value.length > max) {
    throw new HttpError(400, `${key} 格式无效`)
  }
  return value
}

export function normalizeEmail(value: string): string {
  const email = value.trim().toLowerCase()
  if (
    email.length > 254 ||
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(email)
  ) {
    throw new HttpError(400, 'email 格式无效')
  }
  return email
}

export function bearerToken(request: Request): string | null {
  const authorization = request.headers.get('authorization')
  if (!authorization?.startsWith('Bearer ')) return null
  const token = authorization.slice('Bearer '.length).trim()
  return token || null
}
