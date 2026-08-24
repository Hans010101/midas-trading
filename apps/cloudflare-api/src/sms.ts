import { hmacSha256, sha256Hex } from './crypto'
import { HttpError } from './http'

const HOST = 'dypnsapi.aliyuncs.com'

function hex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

function encode(value: string): string {
  return encodeURIComponent(value).replace(/[!'()*]/gu, (character) =>
    `%${character.charCodeAt(0).toString(16).toUpperCase()}`,
  )
}

export function normalizeChinaMobile(value: string): string {
  const compact = value.trim().replace(/[\s()-]/gu, '')
  const national = compact.startsWith('+86')
    ? compact.slice(3)
    : compact.startsWith('86') && compact.length === 13
      ? compact.slice(2)
      : compact
  if (!/^1[3-9]\d{9}$/u.test(national)) {
    throw new HttpError(422, '请输入有效的中国大陆手机号')
  }
  return `+86${national}`
}

async function callSmsApi(
  env: Env,
  action: 'SendSmsVerifyCode' | 'CheckSmsVerifyCode',
  parameters: Readonly<Record<string, string>>,
): Promise<{
  Code?: string
  Message?: string
  Model?: { VerifyResult?: string }
}> {
  if (
    !env.ALIBABA_CLOUD_ACCESS_KEY_ID ||
    !env.ALIBABA_CLOUD_ACCESS_KEY_SECRET ||
    !env.ALIYUN_SMS_SIGN_NAME ||
    !env.ALIYUN_SMS_TEMPLATE_CODE
  ) {
    throw new HttpError(503, '短信服务尚未完成配置')
  }

  const canonicalQuery = Object.entries(parameters)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${encode(key)}=${encode(value)}`)
    .join('&')
  const payloadHash = await sha256Hex('')
  const date = new Date().toISOString().replace(/\.\d{3}Z$/u, 'Z')
  const nonce = crypto.randomUUID()
  const canonicalHeaders =
    `host:${HOST}\n` +
    `x-acs-action:${action}\n` +
    `x-acs-content-sha256:${payloadHash}\n` +
    `x-acs-date:${date}\n` +
    `x-acs-signature-nonce:${nonce}\n` +
    'x-acs-version:2017-05-25\n'
  const signedHeaders =
    'host;x-acs-action;x-acs-content-sha256;x-acs-date;x-acs-signature-nonce;x-acs-version'
  const canonicalRequest =
    `POST\n/\n${canonicalQuery}\n${canonicalHeaders}\n${signedHeaders}\n${payloadHash}`
  const signature = hex(
    await hmacSha256(
      env.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
      `ACS3-HMAC-SHA256\n${await sha256Hex(canonicalRequest)}`,
    ),
  )
  const response = await fetch(`https://${HOST}/?${canonicalQuery}`, {
    method: 'POST',
    headers: {
      authorization:
        `ACS3-HMAC-SHA256 Credential=${env.ALIBABA_CLOUD_ACCESS_KEY_ID},` +
        `SignedHeaders=${signedHeaders},Signature=${signature}`,
      'content-type': 'application/x-www-form-urlencoded',
      'x-acs-action': action,
      'x-acs-content-sha256': payloadHash,
      'x-acs-date': date,
      'x-acs-signature-nonce': nonce,
      'x-acs-version': '2017-05-25',
    },
    body: '',
    signal: AbortSignal.timeout(15_000),
  })
  const result = (await response.json().catch(() => null)) as {
    Code?: string
    Message?: string
    Model?: { VerifyResult?: string }
  } | null
  if (!response.ok || result?.Code !== 'OK') {
    console.error(JSON.stringify({
      event: 'auth.sms_provider_failed',
      status: response.status,
      code: result?.Code ?? 'INVALID_RESPONSE',
      message: result?.Message?.slice(0, 300),
    }))
    if (
      result?.Code === 'FREQUENCY_FAIL' ||
      result?.Code === 'BUSINESS_LIMIT_CONTROL'
    ) {
      throw new HttpError(429, '请求过于频繁，请稍后再试')
    }
    throw new HttpError(502, '短信服务暂时不可用，请稍后重试')
  }
  return result
}

export async function sendSmsCode(
  env: Env,
  phoneE164: string,
): Promise<void> {
  await callSmsApi(env, 'SendSmsVerifyCode', {
    PhoneNumber: phoneE164.slice(3),
    CountryCode: '86',
    SignName: env.ALIYUN_SMS_SIGN_NAME,
    TemplateCode: env.ALIYUN_SMS_TEMPLATE_CODE,
    TemplateParam: JSON.stringify({ code: '##code##', min: '5' }),
    CodeLength: '6',
    CodeType: '1',
    ValidTime: '300',
    DuplicatePolicy: '1',
    Interval: '60',
    ReturnVerifyCode: 'false',
  })
}

export async function checkSmsCode(
  env: Env,
  phoneE164: string,
  code: string,
): Promise<boolean> {
  const result = await callSmsApi(env, 'CheckSmsVerifyCode', {
    PhoneNumber: phoneE164.slice(3),
    CountryCode: '86',
    VerifyCode: code,
  })
  return result.Model?.VerifyResult === 'PASS'
}
