import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  invokeAi,
  parseAiJson,
  WORKERS_AI_MODEL,
} from '../src/ai-provider'

afterEach(() => {
  vi.restoreAllMocks()
})

function aiEnv(
  run: (model: string, input: unknown) => Promise<unknown>,
  deepSeekKey = '',
): Env {
  return {
    AI: { run },
    DEEPSEEK_API_KEY: deepSeekKey,
  } as unknown as Env
}

describe('independent AI provider routing', () => {
  it('uses Cloudflare Workers AI as the primary provider', async () => {
    const run = vi.fn().mockResolvedValue({
      response: '{"score":42}',
      usage: { total_tokens: 19 },
    })

    const result = await invokeAi(aiEnv(run), {
      system: 'system',
      prompt: 'prompt',
    })

    expect(run).toHaveBeenCalledWith(
      WORKERS_AI_MODEL,
      expect.objectContaining({ max_tokens: 700 }),
    )
    expect(result).toMatchObject({
      provider: 'cloudflare-workers-ai',
      fallback_used: false,
      token_usage: 19,
    })
  })

  it('falls back to DeepSeek only when Workers AI fails', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      Response.json({
        choices: [{ message: { content: '{"score":18}' } }],
        usage: { total_tokens: 23 },
      }),
    )

    const result = await invokeAi(
      aiEnv(async () => {
        throw new Error('primary unavailable')
      }, 'independent-deepseek-key'),
      { system: 'system', prompt: 'prompt' },
    )

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(result).toMatchObject({
      provider: 'deepseek',
      model: 'deepseek-chat',
      fallback_used: true,
      token_usage: 23,
    })
  })

  it('parses plain and fenced JSON output', () => {
    expect(parseAiJson('{"score":1}')).toEqual({ score: 1 })
    expect(parseAiJson('```json\n{"score":2}\n```')).toEqual({ score: 2 })
  })
})
