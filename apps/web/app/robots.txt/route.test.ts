import { describe, expect, it } from 'vitest'

import { GET } from './route'

describe('robots.txt', () => {
  it('allows search and AI retrieval while excluding private paths and training crawlers', async () => {
    const body = await GET().text()
    expect(body).toContain('Content-signal: search=yes, ai-input=yes, ai-train=no')
    expect(body).toContain('Disallow: /admin')
    expect(body).toContain('User-agent: GPTBot\nDisallow: /')
    expect(body).not.toContain('User-agent: OAI-SearchBot')
  })
})
