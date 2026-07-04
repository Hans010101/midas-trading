/**
 * 旧阶列表 URL 兜底薄壳(SEO 批2)· /academy/stage?s=x → 308 → /academy/stage/x。
 *
 * ★Next 15 的 redirects() has:[{type:'query'}] 不支持 query 值捕获 → 薄壳 permanentRedirect
 *   是唯一正解(侦察确认)。无 s → 训练营首页。正文渲染全在 [s]/page.tsx(路径段 · 6 阶 SSG)。
 */

import { permanentRedirect, redirect } from 'next/navigation'

export default async function LegacyStageRedirect({
  searchParams,
}: {
  searchParams: Promise<{ s?: string }>
}) {
  const { s } = await searchParams
  if (s) permanentRedirect(`/academy/stage/${s}`)
  redirect('/academy')
}
