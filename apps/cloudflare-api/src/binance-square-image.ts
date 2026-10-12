const IMAGE_ENDPOINT = 'https://www.binance.com/bapi/composite/v2/public/pgc/openApi/image'

export class SquareImageError extends Error {
  readonly kind: 'account' | 'rejected' | 'transient'

  constructor(message: string, kind: SquareImageError['kind'] = 'transient') {
    super(message)
    this.kind = kind
  }
}

async function imageRequest(
  path: string, apiKey: string, body: Record<string, string>, signal: AbortSignal,
): Promise<Record<string, unknown>> {
  const response = await fetch(`${IMAGE_ENDPOINT}/${path}`, {
    method: 'POST',
    headers: {
      'X-Square-OpenAPI-Key': apiKey,
      'content-type': 'application/json',
      clienttype: 'binanceSkill',
    },
    body: JSON.stringify(body),
    signal,
  })
  const raw: unknown = await response.json().catch(() => null)
  const envelope = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
  const code = String(envelope.code ?? '')
  if (!response.ok || !['000000', '0'].includes(code)) {
    const kind = response.status === 401 || response.status === 403 ? 'account'
      : response.status === 429 || response.status >= 500 || !code
        ? 'transient' : code === '20022' ? 'rejected' : 'account'
    const message = typeof envelope.message === 'string' ? envelope.message.slice(0, 300) : '无有效响应'
    throw new SquareImageError(`图片接口 ${path} 失败 [${code || response.status}] ${message}`, kind)
  }
  return envelope.data && typeof envelope.data === 'object'
    ? envelope.data as Record<string, unknown> : {}
}

export async function uploadSquareImage(apiKey: string, bytes: ArrayBuffer, kind = 'chart'): Promise<string> {
  const data = await imageRequest('presignedUrl', apiKey,
    { imageName: `midas-${kind}-${Date.now()}.png` }, AbortSignal.timeout(30_000))
  const url = typeof data.presignedUrl === 'string' ? data.presignedUrl : ''
  const ticket = typeof data.fileTicket === 'string' ? data.fileTicket : ''
  if (!url.startsWith('https://') || !ticket) throw new SquareImageError('图片预签名缺少上传地址或票据')
  const put = await fetch(url, {
    method: 'PUT', headers: { 'content-type': 'image/png' }, body: bytes,
    signal: AbortSignal.timeout(30_000),
  })
  if (!put.ok) throw new SquareImageError(`图片上传 HTTP ${put.status}`)

  // Processing can outlast 30 seconds; bound the whole poll, not just each request.
  const deadline = Date.now() + 120_000
  while (Date.now() < deadline) {
    const status = await imageRequest('imageStatus', apiKey, { fileTicket: ticket },
      AbortSignal.timeout(Math.min(30_000, deadline - Date.now())))
    if (status.status === 1 || status.status === '1') {
      if (typeof status.imageUrl === 'string' && status.imageUrl.startsWith('https://')) return status.imageUrl
      throw new SquareImageError('图片处理完成但缺少有效地址')
    }
    if (status.status === 2 || status.status === '2') {
      const reason = typeof status.failedReason === 'string' ? status.failedReason.slice(0, 300) : '上游未提供原因'
      throw new SquareImageError(`图片处理被拒绝：${reason}`, 'rejected')
    }
    await new Promise((resolve) => setTimeout(resolve, Math.min(3_000, Math.max(0, deadline - Date.now()))))
  }
  throw new SquareImageError('图片处理超时（已等待 120 秒，将在后续发布轮次重试）')
}
