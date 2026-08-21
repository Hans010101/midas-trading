/**
 * /llms-full.txt(SEO 批4 · GEO 内容件 · D4 定案:开放全文供 AI 引擎一次抓取)。
 *
 * 内容 = llms.txt 同款头部 + 名词词典全文 + 训练营全部文章正文(按六阶 · order 升序拼接,
 * 每篇带标题 / 阶 / canonical URL 元行)。全部内容本就免费公开全量 HTML,此处仅改变打包
 * 形态,增量暴露 ≈ 0(审计 D4 结论)。构建期静态生成(force-static · fs 读发生在 build)。
 *
 * ★红线:免责措辞逐字复用现有合规文案(词典页头免责原样保留在词典段内)· 无买卖祈使词。
 * ★manifest 条目多于实体 md 文件时(案例库等复用),getArticleBySlug 返 null 自然跳过 + 去重。
 */
import { getArticleBySlug, getGlossary } from '@/lib/academy'
import { ACADEMY_ARTICLES, ACADEMY_STAGES } from '@/content/academy/manifest'
import { PRODUCTION_WEB_URL } from '@/lib/site'

export const dynamic = 'force-static'

const BASE = PRODUCTION_WEB_URL

export function GET(): Response {
  const parts: string[] = []

  parts.push(`# Midas Trading（点金 Midas）· 训练营与词典全文(llms-full)

> Midas Trading(${BASE})是 AI 原生的跨市场(加密 / 美股 / A股 / 港股)分析与交易
> 学习终端:全程虚拟资金,不涉及任何真实交易。本文件为训练营全部教学文章与名词词典的
> 完整正文,仅供学习参考,不构成任何形式的投资建议;不预测价格、不保证盈利。
> 索引版见 ${BASE}/llms.txt · 网页版见 ${BASE}/academy`)

  // ── 词典全文(自带页头免责)──
  parts.push(`\n\n================================================================
# 第一部分 · 交易名词词典
来源:${BASE}/academy/glossary
================================================================\n`)
  parts.push(getGlossary())

  // ── 118 篇文章 · 按阶 → order 拼接(slug 去重 · 缺文件跳过)──
  const seen = new Set<string>()
  for (const stage of ACADEMY_STAGES) {
    const articles = ACADEMY_ARTICLES.filter((a) => a.stage === stage.slug).sort(
      (a, b) => a.order - b.order,
    )
    parts.push(`\n\n================================================================
# ${stage.stageLabel} · ${stage.name}
${stage.desc}
================================================================`)
    for (const a of articles) {
      if (seen.has(a.slug)) continue
      seen.add(a.slug)
      const md = getArticleBySlug(a.slug)
      if (md === null) continue // manifest 条目无对应 md(案例库复用等)→ 跳过
      parts.push(`\n\n---
标题:${a.title}
出处:${BASE}/academy/article/${a.slug}(点金训练营 · ${stage.stageLabel} ${stage.name})
---\n
${md.trim()}`)
    }
  }

  parts.push(`\n\n================================================================
以上全部内容 © Midas Trading(${BASE})· 仅供学习参考,不构成投资建议。
================================================================\n`)

  return new Response(parts.join('\n'), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  })
}
