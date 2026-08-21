import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const ROOT = process.cwd()
const ACTIVE_ROOTS = ['apps/cloudflare-api', 'apps/web']
const FORBIDDEN = [
  { label: '阿里云运行时', pattern: /阿里云|aliyun/giu },
  { label: '旧 VPS 流水线', pattern: /deploy\.yml|香港 VPS/giu },
]
const ALLOWED_FILES = new Set([
  // 迁移期唯一旧 API 出口；全部余项迁完后删除。
  'apps/web/app/api-proxy/[...path]/route.ts',
  'apps/web/wrangler.jsonc',
  'apps/web/cloudflare-env.d.ts',
  // 独立 Resend Key 使用的已验证发件域，不代表旧项目运行时依赖。
  'apps/cloudflare-api/wrangler.jsonc',
])

async function listFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const absolute = path.join(directory, entry.name)
      if (entry.isDirectory()) {
        if (
          entry.name === 'node_modules' ||
          entry.name === '.next' ||
          entry.name === '.open-next' ||
          entry.name === 'dist'
        ) {
          return []
        }
        return listFiles(absolute)
      }
      return [absolute]
    }),
  )
  return nested.flat()
}

const files = (
  await Promise.all(ACTIVE_ROOTS.map((root) => listFiles(path.join(ROOT, root))))
).flat()
const violations = []

for (const absolute of files) {
  const relative = path.relative(ROOT, absolute)
  if (
    ALLOWED_FILES.has(relative) ||
    /\.test\.[cm]?[jt]sx?$/u.test(relative) ||
    !/\.(?:[cm]?[jt]sx?|jsonc?|md)$/u.test(relative)
  ) {
    continue
  }
  const source = await readFile(absolute, 'utf8')
  for (const rule of FORBIDDEN) {
    if (rule.pattern.test(source)) {
      violations.push(`${relative}: ${rule.label}`)
    }
    rule.pattern.lastIndex = 0
  }
}

if (violations.length > 0) {
  console.error('检测到新增的旧 Midas / 阿里云生产依赖：')
  for (const violation of violations) console.error(`- ${violation}`)
  process.exitCode = 1
} else {
  console.log('Midas Trading Cloudflare 边界检查通过')
}
