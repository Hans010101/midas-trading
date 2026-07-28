import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  cloudflareTest,
  readD1Migrations,
} from '@cloudflare/vitest-pool-workers'
import { defineConfig } from 'vitest/config'

const projectDir = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [
    cloudflareTest(async () => ({
      wrangler: {
        // The production config contains a real Workers AI binding. Tests use
        // an explicit local config and inject their own AI stub so CI never
        // opens a remote proxy session or consumes production allocation.
        configPath: path.join(projectDir, 'wrangler.test.jsonc'),
      },
      miniflare: {
        bindings: {
          TEST_MIGRATIONS: await readD1Migrations(
            path.join(projectDir, 'migrations'),
          ),
          RESEND_API_KEY: 'test-resend-key',
          SUPPORT_EMAIL_TO: 'support@example.test',
          PASSWORD_PEPPER: 'test-password-pepper-with-sufficient-entropy',
        },
      },
    })),
  ],
  test: {
    include: ['test/**/*.test.ts'],
    setupFiles: ['./test/apply-migrations.ts'],
  },
})
