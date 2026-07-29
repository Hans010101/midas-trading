const CONTENT_ENDPOINT =
  'https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add'

type BinanceSquareEnv = Readonly<{
  BINANCE_SQUARE_API_KEY?: string
}>

type BinanceEnvelope = Readonly<{
  code?: unknown
  message?: unknown
  messageDetail?: unknown
  success?: unknown
  data?: unknown
}>

export type BinanceSquarePublishResult = Readonly<{
  success: boolean
  postId: string | null
  url: string | null
  error: string | null
}>

export function binanceSquareEnabled(env: Env): boolean {
  return Boolean((env as Env & BinanceSquareEnv).BINANCE_SQUARE_API_KEY?.trim())
}

function postIdentity(data: unknown): { postId: string | null; url: string | null } {
  if (typeof data !== 'object' || data === null) {
    const postId = typeof data === 'string' || typeof data === 'number'
      ? String(data)
      : null
    return {
      postId,
      url: postId ? `https://www.binance.com/square/post/${postId}` : null,
    }
  }
  const item = data as Record<string, unknown>
  const rawId = item.id ?? item.contentId ?? item.postId ?? item.post_id
  const postId = typeof rawId === 'string' || typeof rawId === 'number'
    ? String(rawId)
    : null
  const rawUrl = item.shareLink ?? item.shareUrl ?? item.url
  const url = typeof rawUrl === 'string' && rawUrl.startsWith('https://')
    ? rawUrl
    : postId
      ? `https://www.binance.com/square/post/${postId}`
      : null
  return { postId, url }
}

function safeMessage(body: BinanceEnvelope): string {
  const message = body.message ?? body.messageDetail
  return typeof message === 'string' && message.trim()
    ? message.trim().slice(0, 500)
    : '币安广场拒绝发布请求'
}

export async function publishToBinanceSquare(
  env: Env,
  text: string,
): Promise<BinanceSquarePublishResult> {
  const apiKey = (env as Env & BinanceSquareEnv).BINANCE_SQUARE_API_KEY?.trim()
  if (!apiKey) {
    return {
      success: false,
      postId: null,
      url: null,
      error: '币安广场发布凭证尚未配置',
    }
  }

  let response: Response
  try {
    response = await fetch(CONTENT_ENDPOINT, {
      method: 'POST',
      headers: {
        'X-Square-OpenAPI-Key': apiKey,
        'content-type': 'application/json',
        clienttype: 'binanceSkill',
      },
      body: JSON.stringify({
        contentType: 1,
        bodyTextOnly: [...text.trim()].slice(0, 4_000).join(''),
      }),
      signal: AbortSignal.timeout(30_000),
    })
  } catch (error) {
    return {
      success: false,
      postId: null,
      url: null,
      error: `币安广场网络错误：${error instanceof Error ? error.name : 'unknown'}`,
    }
  }

  // Binance's official Square skill documents a 504 edge case where the post
  // was accepted but its id was not returned. Treat it as a successful publish
  // so an automatic retry cannot create a duplicate public post.
  if (response.status === 504) {
    return { success: true, postId: null, url: null, error: null }
  }

  let body: BinanceEnvelope
  try {
    body = await response.json() as BinanceEnvelope
  } catch {
    return {
      success: false,
      postId: null,
      url: null,
      error: `币安广场返回非 JSON 响应（HTTP ${response.status}）`,
    }
  }
  const code = String(body.code ?? '')
  const success = response.ok && (body.success === true || code === '000000' || code === '0')
  if (!success) {
    return {
      success: false,
      postId: null,
      url: null,
      error: `币安广场拒绝 [${code || response.status}] ${safeMessage(body)}`,
    }
  }
  const identity = postIdentity(body.data)
  return {
    success: true,
    postId: identity.postId,
    url: identity.url,
    error: null,
  }
}
