import { Buffer } from 'node:buffer'

import { authenticate } from './auth'
import { HttpError, jsonResponse, normalizeEmail } from './http'

const ALLOWED_CATEGORIES = new Set([
  'not_received',
  'duplicate_charge',
  'activation_failed',
  'other',
])
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png'])
const MAX_DESCRIPTION_LENGTH = 2_000
const MAX_IMAGES = 3
const MAX_IMAGE_BYTES = 2 * 1024 * 1024
const MAX_MULTIPART_BYTES = 7 * 1024 * 1024

function optionalFormString(
  form: FormData,
  key: string,
  maxLength: number,
): string | null {
  const value = form.get(key)
  if (value === null || value === '') return null
  if (typeof value !== 'string') {
    throw new HttpError(422, `${key} 格式无效`)
  }
  const normalized = value.trim()
  if (!normalized || normalized.length > maxLength) {
    throw new HttpError(422, `${key} 格式无效`)
  }
  return normalized
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/gu, (character) => {
    const replacements: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }
    return replacements[character] ?? character
  })
}

async function notifySupport(
  env: Env,
  ticket: Readonly<{
    id: number
    userId: string
    accountEmail: string
    contactEmail: string
    category: string
    description: string
    relatedOrderId: string | null
    createdAt: number
  }>,
  images: readonly File[],
): Promise<boolean> {
  if (!env.SUPPORT_EMAIL_TO || !env.RESEND_API_KEY) return false

  const attachments = await Promise.all(
    images.map(async (image) => ({
      filename: image.name || 'image',
      content: Buffer.from(await image.arrayBuffer()).toString('base64'),
    })),
  )
  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      authorization: `Bearer ${env.RESEND_API_KEY}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      from: env.EMAIL_FROM,
      to: [env.SUPPORT_EMAIL_TO],
      subject: `[Midas Trading 工单] ${ticket.category} · #${ticket.id}`,
      html: `
        <div style="font-family:Arial,'Noto Sans SC',sans-serif;max-width:620px">
          <h2>Midas Trading 工单 #${ticket.id}</h2>
          <p><b>用户：</b>${escapeHtml(ticket.userId)}</p>
          <p><b>账号邮箱：</b>${escapeHtml(ticket.accountEmail)}</p>
          <p><b>联系邮箱：</b>${escapeHtml(ticket.contactEmail)}</p>
          <p><b>类型：</b>${escapeHtml(ticket.category)}</p>
          ${ticket.relatedOrderId ? `<p><b>关联订单：</b>${escapeHtml(ticket.relatedOrderId)}</p>` : ''}
          <p><b>描述：</b></p>
          <p style="white-space:pre-wrap">${escapeHtml(ticket.description)}</p>
          <p style="color:#666">提交时间：${new Date(ticket.createdAt).toISOString()}</p>
        </div>
      `,
      ...(attachments.length > 0 ? { attachments } : {}),
    }),
  })
  return response.ok
}

async function submitTicket(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const contentLength = Number(request.headers.get('content-length') ?? '0')
  if (contentLength > MAX_MULTIPART_BYTES) {
    throw new HttpError(413, '上传内容过大')
  }
  const auth = await authenticate(request, env)
  const form = await request.formData()
  const category = optionalFormString(form, 'category', 32)
  if (!category || !ALLOWED_CATEGORIES.has(category)) {
    throw new HttpError(422, '未知工单类型')
  }
  const description = optionalFormString(
    form,
    'description',
    MAX_DESCRIPTION_LENGTH,
  )
  if (!description) throw new HttpError(422, '问题描述不能为空')

  const suppliedEmail = optionalFormString(form, 'contact_email', 254)
  const contactEmail = suppliedEmail
    ? normalizeEmail(suppliedEmail)
    : auth.user.email
  const relatedOrderId = optionalFormString(form, 'related_order_id', 64)
  const images = form
    .getAll('images')
    .filter((value): value is File => value instanceof File && value.name !== '')
  if (images.length > MAX_IMAGES) {
    throw new HttpError(422, `最多上传 ${MAX_IMAGES} 张图片`)
  }
  for (const image of images) {
    if (!ALLOWED_IMAGE_TYPES.has(image.type)) {
      throw new HttpError(422, '仅支持 JPG 或 PNG 图片')
    }
    if (image.size > MAX_IMAGE_BYTES) {
      throw new HttpError(422, '单张图片不能超过 2 MB')
    }
  }

  const createdAt = Date.now()
  const result = await env.DB
    .prepare(
      `INSERT INTO support_tickets
        (user_id, contact_email, category, description, related_order_id,
         image_count, status, created_at)
       VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
       RETURNING id`,
    )
    .bind(
      auth.user.id,
      contactEmail,
      category,
      description,
      relatedOrderId,
      images.length,
      createdAt,
    )
    .first<{ id: number }>()
  if (!result) throw new HttpError(500, '工单创建失败')

  let emailSent = false
  try {
    emailSent = await notifySupport(
      env,
      {
        id: result.id,
        userId: auth.user.id,
        accountEmail: auth.user.email,
        contactEmail,
        category,
        description,
        relatedOrderId,
        createdAt,
      },
      images,
    )
  } catch (error) {
    console.error(
      JSON.stringify({
        event: 'support.email.failed',
        ticketId: result.id,
        error: error instanceof Error ? error.message : String(error),
      }),
    )
  }

  return jsonResponse(
    {
      ticket_id: result.id,
      status: 'open',
      message: emailSent
        ? '工单已提交，我们会通过邮件与你联系'
        : '工单已记录，邮件通知可能延迟',
      email_sent: emailSent,
    },
    200,
    requestId,
    request.method,
  )
}

export async function handleSupportRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (!path.startsWith('/api/v1/support/')) return null
  if (path === '/api/v1/support/ticket' && request.method === 'POST') {
    return submitTicket(request, env, requestId)
  }
  return jsonResponse(
    { detail: 'Route not found' },
    404,
    requestId,
    request.method,
  )
}
