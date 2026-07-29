const CONTENT_ENDPOINT =
  'https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add'
const IMAGE_PRESIGN_ENDPOINT =
  'https://www.binance.com/bapi/composite/v2/public/pgc/openApi/image/presignedUrl'
const IMAGE_STATUS_ENDPOINT =
  'https://www.binance.com/bapi/composite/v2/public/pgc/openApi/image/imageStatus'

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
  imageUrl: string | null
  imageError: string | null
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

function headers(apiKey: string): Record<string, string> {
  return {
    'X-Square-OpenAPI-Key': apiKey,
    'content-type': 'application/json',
    clienttype: 'binanceSkill',
  }
}

async function uploadImage(apiKey: string, bytes: ArrayBuffer): Promise<string> {
  const presignResponse = await fetch(IMAGE_PRESIGN_ENDPOINT, {
    method: 'POST',
    headers: headers(apiKey),
    body: JSON.stringify({ imageName: `midas-chart-${Date.now()}.png` }),
    signal: AbortSignal.timeout(30_000),
  })
  const presign = await presignResponse.json() as BinanceEnvelope
  const data = typeof presign.data === 'object' && presign.data !== null
    ? presign.data as Record<string, unknown>
    : {}
  const url = typeof data.presignedUrl === 'string' ? data.presignedUrl : ''
  const ticket = typeof data.fileTicket === 'string' ? data.fileTicket : ''
  if (!presignResponse.ok || !url || !ticket) {
    throw new Error(`图片预签名失败 [${String(presign.code ?? presignResponse.status)}]`)
  }
  const put = await fetch(url, {
    method: 'PUT',
    headers: { 'content-type': 'image/png' },
    body: bytes,
    signal: AbortSignal.timeout(30_000),
  })
  if (!put.ok) throw new Error(`图片上传 HTTP ${put.status}`)
  for (let attempt = 0; attempt < 15; attempt += 1) {
    const statusResponse = await fetch(IMAGE_STATUS_ENDPOINT, {
      method: 'POST',
      headers: headers(apiKey),
      body: JSON.stringify({ fileTicket: ticket }),
      signal: AbortSignal.timeout(30_000),
    })
    const status = await statusResponse.json() as BinanceEnvelope
    const statusData = typeof status.data === 'object' && status.data !== null
      ? status.data as Record<string, unknown>
      : {}
    if (statusData.status === 1 && typeof statusData.imageUrl === 'string') {
      return statusData.imageUrl
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000))
  }
  throw new Error('图片处理超时')
}

export async function publishToBinanceSquare(
  env: Env,
  text: string,
  imageBytes?: ArrayBuffer | null,
): Promise<BinanceSquarePublishResult> {
  const apiKey = (env as Env & BinanceSquareEnv).BINANCE_SQUARE_API_KEY?.trim()
  if (!apiKey) {
    return {
      success: false,
      postId: null,
      url: null,
      error: '币安广场发布凭证尚未配置',
      imageUrl: null,
      imageError: null,
    }
  }

  let imageUrl: string | null = null
  let imageError: string | null = null
  if (imageBytes && imageBytes.byteLength > 0) {
    try {
      imageUrl = await uploadImage(apiKey, imageBytes)
    } catch (error) {
      // Image is an enhancement. A rendering/upload outage must not stop the
      // already-vetted market post from being published as text.
      imageError = error instanceof Error ? error.message : '图片上传失败'
      console.error(JSON.stringify({ event: 'binance.image_failed', error: imageError }))
    }
  }

  let response: Response
  try {
    response = await fetch(CONTENT_ENDPOINT, {
      method: 'POST',
      headers: headers(apiKey),
      body: JSON.stringify({
        contentType: 1,
        bodyTextOnly: [...text.trim()].slice(0, 4_000).join(''),
        ...(imageUrl ? { imageList: [imageUrl] } : {}),
      }),
      signal: AbortSignal.timeout(30_000),
    })
  } catch (error) {
    return {
      success: false,
      postId: null,
      url: null,
      error: `币安广场网络错误：${error instanceof Error ? error.name : 'unknown'}`,
      imageUrl,
      imageError,
    }
  }

  // Binance's official Square skill documents a 504 edge case where the post
  // was accepted but its id was not returned. Treat it as a successful publish
  // so an automatic retry cannot create a duplicate public post.
  if (response.status === 504) {
    return { success: true, postId: null, url: null, error: null, imageUrl, imageError }
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
      imageUrl,
      imageError,
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
      imageUrl,
      imageError,
    }
  }
  const identity = postIdentity(body.data)
  return {
    success: true,
    postId: identity.postId,
    url: identity.url,
    error: null,
    imageUrl,
    imageError,
  }
}
