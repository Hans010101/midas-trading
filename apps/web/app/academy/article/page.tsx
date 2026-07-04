/**
 * 旧文章 URL 兜底薄壳(SEO 批2)· /academy/article?slug=X → 308 → /academy/article/X。
 *
 * ★Next 15 的 redirects() has:[{type:'query'}] 不支持 query 值捕获 → 薄壳 permanentRedirect
 *   是唯一正解(侦察确认)。保留全部旧收藏/分享/外链的权重传递;无 slug → 训练营首页。
 * 正文渲染全在 [slug]/page.tsx(路径段 · 118 篇 SSG)。
 */

import { permanentRedirect, redirect } from 'next/navigation'

export default async function LegacyArticleRedirect({
  searchParams,
}: {
  searchParams: Promise<{ slug?: string }>
}) {
  const { slug } = await searchParams
  if (slug) permanentRedirect(`/academy/article/${slug}`)
  redirect('/academy')
}
