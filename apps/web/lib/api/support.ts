/**
 * 支付工单 API client(support 模块 · 技术故障客服通道)· 照 payment.ts Bearer 范式。
 *
 * - POST /support/ticket  multipart:类型 + 描述 + 联系邮箱 + 关联订单 + 图片(0-3)
 *
 * 🔴 红线:前端只提交;图片随 multipart 上传,后端走 Resend 邮件附件不落盘。
 * ★ 不手动设 Content-Type —— 让浏览器为 FormData 自动带 multipart boundary。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type TicketCategory =
  | 'not_received'
  | 'duplicate_charge'
  | 'activation_failed'
  | 'other'

export interface SubmitTicketInput {
  category: TicketCategory
  description: string
  contactEmail?: string
  relatedOrderId?: string
  images: File[]
}

export interface TicketCreateOut {
  ticket_id: number
  status: string
  message: string
  email_sent: boolean
}

export class SupportApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`SupportApi ${status}: ${detail}`)
    this.name = 'SupportApiError'
  }
}

async function readDetail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : `HTTP ${resp.status}`
  } catch {
    return `HTTP ${resp.status}`
  }
}

export async function submitTicket(
  token: string, input: SubmitTicketInput,
): Promise<TicketCreateOut> {
  const fd = new FormData()
  fd.append('category', input.category)
  fd.append('description', input.description)
  if (input.contactEmail) fd.append('contact_email', input.contactEmail)
  if (input.relatedOrderId) fd.append('related_order_id', input.relatedOrderId)
  for (const img of input.images) fd.append('images', img)

  const r = await fetch(`${API_BASE}/api/v1/support/ticket`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` }, // ★ 不设 Content-Type,浏览器自带 boundary
    body: fd,
  })
  if (!r.ok) throw new SupportApiError(r.status, await readDetail(r))
  return (await r.json()) as TicketCreateOut
}
