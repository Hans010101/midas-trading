import { HttpError } from './http'

export const WORKERS_AI_MODEL = '@cf/zai-org/glm-4.7-flash' as const
const DEEPSEEK_MODEL = 'deepseek-chat'

export type AiProviderResult = Readonly<{
  content: string
  provider: 'cloudflare-workers-ai' | 'deepseek' | 'technical-rules'
  model: string
  fallback_used: boolean
  token_usage: number
}>

type ChatMessage = Readonly<{
  role: 'system' | 'user'
  content: string
}>

function textContent(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (!Array.isArray(value)) return ''
  return value
    .flatMap((block) => {
      if (typeof block === 'string') return [block]
      if (typeof block !== 'object' || block === null) return []
      const text = (block as { text?: unknown }).text
      return typeof text === 'string' ? [text] : []
    })
    .join('')
    .trim()
}

function contentFromWorkersAi(output: unknown): string {
  if (typeof output !== 'object' || output === null) return ''
  const result = output as {
    response?: unknown
    output_text?: unknown
    choices?: Array<{
      text?: unknown
      message?: { content?: unknown }
    }>
  }
  return (
    textContent(result.response) ||
    textContent(result.output_text) ||
    textContent(result.choices?.[0]?.message?.content) ||
    textContent(result.choices?.[0]?.text)
  )
}

function emptyOutputMetadata(output: unknown) {
  if (typeof output !== 'object' || output === null) {
    return { output_type: typeof output }
  }
  const result = output as {
    choices?: Array<{
      finish_reason?: unknown
      message?: Record<string, unknown>
    }>
    usage?: unknown
  }
  return {
    output_keys: Object.keys(output),
    choice_count: result.choices?.length ?? 0,
    finish_reason: result.choices?.[0]?.finish_reason ?? null,
    message_keys: result.choices?.[0]?.message
      ? Object.keys(result.choices[0].message)
      : [],
    usage: result.usage ?? null,
  }
}

function tokenUsageFrom(output: unknown): number {
  if (typeof output !== 'object' || output === null) return 0
  const usage = (output as {
    usage?: {
      total_tokens?: unknown
      prompt_tokens?: unknown
      completion_tokens?: unknown
    }
  }).usage
  if (typeof usage?.total_tokens === 'number') return usage.total_tokens
  return Number(usage?.prompt_tokens ?? 0) + Number(usage?.completion_tokens ?? 0)
}

async function workersAi(
  env: Env,
  messages: readonly ChatMessage[],
  maxTokens: number,
  temperature: number,
): Promise<AiProviderResult> {
  const output = await env.AI.run(WORKERS_AI_MODEL, {
    messages: [...messages],
    max_completion_tokens: maxTokens,
    temperature,
    response_format: { type: 'json_object' },
    chat_template_kwargs: { enable_thinking: false },
  })
  const content = contentFromWorkersAi(output)
  if (!content) {
    console.warn(JSON.stringify({
      event: 'ai.empty_output',
      provider: 'cloudflare-workers-ai',
      model: WORKERS_AI_MODEL,
      ...emptyOutputMetadata(output),
    }))
    throw new Error('Workers AI returned empty content')
  }
  return {
    content,
    provider: 'cloudflare-workers-ai',
    model: WORKERS_AI_MODEL,
    fallback_used: false,
    token_usage: tokenUsageFrom(output),
  }
}

async function deepSeek(
  apiKey: string,
  messages: readonly ChatMessage[],
  maxTokens: number,
  temperature: number,
): Promise<AiProviderResult> {
  const response = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: {
      authorization: `Bearer ${apiKey}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: DEEPSEEK_MODEL,
      messages,
      max_tokens: maxTokens,
      temperature,
      response_format: { type: 'json_object' },
    }),
    signal: AbortSignal.timeout(25_000),
  })
  if (!response.ok) {
    throw new Error(`DeepSeek HTTP ${response.status}`)
  }
  const output = (await response.json()) as {
    choices?: Array<{ message?: { content?: unknown } }>
    usage?: { total_tokens?: unknown }
  }
  const content = output.choices?.[0]?.message?.content
  if (typeof content !== 'string' || !content.trim()) {
    throw new Error('DeepSeek returned empty content')
  }
  return {
    content: content.trim(),
    provider: 'deepseek',
    model: DEEPSEEK_MODEL,
    fallback_used: true,
    token_usage: Number(output.usage?.total_tokens ?? 0),
  }
}

export async function invokeAi(
  env: Env,
  input: Readonly<{
    system: string
    prompt: string
    maxTokens?: number
    temperature?: number
  }>,
): Promise<AiProviderResult> {
  const messages: readonly ChatMessage[] = [
    { role: 'system', content: input.system },
    { role: 'user', content: input.prompt },
  ]
  const maxTokens = input.maxTokens ?? 700
  const temperature = input.temperature ?? 0.2
  try {
    return await workersAi(env, messages, maxTokens, temperature)
  } catch (primaryError) {
    console.warn(JSON.stringify({
      event: 'ai.primary_failed',
      provider: 'cloudflare-workers-ai',
      model: WORKERS_AI_MODEL,
      error:
        primaryError instanceof Error ? primaryError.message : String(primaryError),
    }))
    const apiKey = env.DEEPSEEK_API_KEY?.trim()
    if (!apiKey) {
      throw new HttpError(
        503,
        'Cloudflare AI 当前不可用，DeepSeek 备用通道尚未配置',
      )
    }
    try {
      return await deepSeek(apiKey, messages, maxTokens, temperature)
    } catch (fallbackError) {
      console.error(JSON.stringify({
        event: 'ai.fallback_failed',
        provider: 'deepseek',
        error:
          fallbackError instanceof Error
            ? fallbackError.message
            : String(fallbackError),
      }))
      throw new HttpError(503, 'AI 主通道与备用通道均暂不可用')
    }
  }
}

export function parseAiJson(content: string): Record<string, unknown> {
  const fenced = content.match(/```(?:json)?\s*([\s\S]*?)```/iu)?.[1]
  const candidate = (fenced ?? content).trim()
  try {
    const value = JSON.parse(candidate) as unknown
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      return value as Record<string, unknown>
    }
  } catch {
    const start = candidate.indexOf('{')
    const end = candidate.lastIndexOf('}')
    if (start >= 0 && end > start) {
      const value = JSON.parse(candidate.slice(start, end + 1)) as unknown
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        return value as Record<string, unknown>
      }
    }
  }
  throw new HttpError(502, 'AI 输出格式异常，请重试')
}
