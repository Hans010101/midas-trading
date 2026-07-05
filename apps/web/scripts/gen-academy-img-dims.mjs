// 生成训练营配图尺寸清单 · SEO webp 小刀。
//
// 背景:训练营 371 张配图原走裸 <img>(不经 /_next/image 优化器 → 生产直发 PNG,
// 单图 ~166KB)。改走 next/image 后优化器自动出 webp(实测 750px 仅 8.8KB · 省 95%),
// 但 next/image 必须知道每张图的 width/height(否则布局抖动/失真)。
// markdown 里只有 src 路径没有尺寸 → 本脚本预生成「src → {w,h}」清单供 renderer 查表。
//
// 无依赖:直接读 PNG 头。PNG = 8 字节签名 + IHDR chunk(4 长度 + 4 类型 "IHDR"
// + 4 宽度 BE + 4 高度 BE),故 width @ 偏移 16、height @ 偏移 20。
//
// 用法:node apps/web/scripts/gen-academy-img-dims.mjs(在 apps/web 下亦可)。
// 新增配图后重跑本脚本刷新清单;未在清单里的图 renderer 会裸 <img> 兜底(不破)。

import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const WEB_ROOT = join(HERE, '..')
const IMG_DIR = join(WEB_ROOT, 'public', 'academy-img')
const OUT = join(WEB_ROOT, 'lib', 'academy-img-dims.ts')

const PNG_SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])

/** 读单张 PNG 的 {w,h};非法 PNG 返回 null(跳过 · 裸 img 兜底)。 */
function pngSize(buf) {
  if (buf.length < 24 || !buf.subarray(0, 8).equals(PNG_SIG)) return null
  if (buf.toString('ascii', 12, 16) !== 'IHDR') return null
  return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) }
}

const files = readdirSync(IMG_DIR)
  .filter((f) => f.toLowerCase().endsWith('.png'))
  .sort()

const entries = []
let skipped = 0
for (const f of files) {
  const size = pngSize(readFileSync(join(IMG_DIR, f)))
  if (!size) {
    skipped++
    console.warn(`跳过(非法 PNG 头):${f}`)
    continue
  }
  // key = markdown 里的 src(public 根 → /academy-img/xxx.png)
  entries.push([`/academy-img/${f}`, size])
}

const body = entries
  .map(([src, { w, h }]) => `  ${JSON.stringify(src)}: { w: ${w}, h: ${h} },`)
  .join('\n')

const out = `// ⚠ 本文件由 scripts/gen-academy-img-dims.mjs 自动生成 · 请勿手改。
// 训练营配图尺寸清单(SEO webp 小刀)· 供 article-renderer 查表走 next/image 优化器。
// 新增配图后重跑:node apps/web/scripts/gen-academy-img-dims.mjs

export type AcademyImgDim = { w: number; h: number }

export const ACADEMY_IMG_DIMS: Record<string, AcademyImgDim> = {
${body}
}
`

writeFileSync(OUT, out, 'utf8')
console.log(`✅ 写入 ${OUT}`)
console.log(`   收录 ${entries.length} 张 · 跳过 ${skipped} 张 · 共扫 ${files.length} 个 .png`)
