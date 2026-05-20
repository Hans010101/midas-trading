/**
 * NextAuth v5 catch-all route handler.
 * 暴露 /api/auth/signin / signout / callback / session 等内置端点。
 */

import { handlers } from '@/auth'

export const { GET, POST } = handlers
