import { HttpError } from './http'

export async function sendVerificationEmail(
  env: Env,
  recipient: string,
  token: string,
): Promise<void> {
  const verifyUrl = `${env.PUBLIC_WEB_URL}/verify-email?token=${encodeURIComponent(token)}`
  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      authorization: `Bearer ${env.RESEND_API_KEY}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      from: env.EMAIL_FROM,
      to: [recipient],
      subject: '验证你的邮箱 · Midas Trading',
      html: `
        <div style="font-family:Arial,'Noto Sans SC',sans-serif;max-width:560px;margin:0 auto;color:#171717">
          <h1 style="font-family:'Noto Serif SC',serif;color:#C8102E">Midas Trading</h1>
          <p>欢迎注册 Midas Trading。请点击下面按钮完成邮箱验证（链接 24 小时有效）：</p>
          <p style="margin:28px 0">
            <a href="${verifyUrl}" style="display:inline-block;padding:12px 28px;background:#C8102E;color:#fff;text-decoration:none">验证邮箱</a>
          </p>
          <p>如果按钮无法点击，请复制下面链接到浏览器：</p>
          <p style="overflow-wrap:anywhere">${verifyUrl}</p>
          <hr style="border:0;border-top:1px solid #eee;margin:28px 0">
          <p style="color:#666;font-size:13px">Midas Trading · 仅供参考，不构成投资建议。</p>
        </div>
      `,
    }),
  })

  if (!response.ok) {
    const detail = (await response.text()).slice(0, 1_000)
    console.error(
      JSON.stringify({
        event: 'email.verification.failed',
        status: response.status,
        detail,
      }),
    )
    throw new HttpError(502, '验证邮件发送失败，请稍后重试')
  }
}
