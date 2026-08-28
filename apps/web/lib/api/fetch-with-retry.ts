const TRANSIENT_STATUS = new Set([408, 425, 429, 500, 502, 503, 504])

/** Read-only market requests get one short retry for transient network/upstream failures. */
export async function fetchWithRetry(
  input: Parameters<typeof fetch>[0],
  init?: Parameters<typeof fetch>[1],
): Promise<Response> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const response = await fetch(input, init)
      if (attempt === 1 || !TRANSIENT_STATUS.has(response.status)) return response
      await response.body?.cancel()
    } catch (error) {
      if (attempt === 1 || init?.signal?.aborted) throw error
    }

    await new Promise((resolve) => setTimeout(resolve, 250))
  }

  throw new Error('Unreachable')
}
