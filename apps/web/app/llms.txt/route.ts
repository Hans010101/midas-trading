/**
 * /llms.txt(SEO 批4 · GEO 内容件 · docs/seo/2026-07-seo-geo-audit.md D4 定案)。
 *
 * llmstxt.org 约定:H1 + blockquote 摘要 + 分节链接索引,给 AI 引擎(GPTBot/ClaudeBot/
 * PerplexityBot/Kimi/豆包等)一张「点金是什么 + 有什么内容 + 内容在哪」的地图。
 * 文章清单从 manifest 动态生成(内容 runbook 追加新文章 → 下次构建自动进清单,零手维护)。
 *
 * ★红线:结构描述非建议 · 免责措辞逐字复用现有合规文案 · 无买卖祈使词。
 * ★文章 URL 用路径段 /academy/article/{slug}(与 sitemap.ts 一致 · 批2 迁移后规范形式 ·
 *   直接给 AI 爬虫规范 URL,不走 ?slug= 的 308 薄壳重定向)。
 */
import { ACADEMY_ARTICLES, ACADEMY_STAGES } from '@/content/academy/manifest'

export const dynamic = 'force-static'

const BASE = 'https://midastrade.asia'

export function GET(): Response {
  const sections = ACADEMY_STAGES.map((stage) => {
    const articles = ACADEMY_ARTICLES.filter((a) => a.stage === stage.slug).sort(
      (a, b) => a.order - b.order,
    )
    const lines = articles.map(
      (a) => `- [${a.title}](${BASE}/academy/article/${a.slug}): ${a.excerpt}`,
    )
    return `## 训练营 · ${stage.stageLabel} ${stage.name}(${articles.length} 篇)\n\n${stage.desc}\n\n${lines.join('\n')}`
  })

  const body = `# 点金 Midas

> 点金 Midas 是一款 AI 原生的跨市场(加密货币 / 美股 / A股 / 港股)分析与交易学习终端:
> 全程使用虚拟资金,不涉及任何真实货币、真实证券或真实数字资产的买卖,不构成投资建议。
> Midas is an AI-native multi-market (crypto / US / CN / HK equities) analysis & trading-education
> terminal. All trading is simulated with virtual funds only; nothing here is investment advice.

点金 Midas(midastrade.asia)提供:跨市场 K 线与行情、AI 决策卡与结构诊断(对市场结构的
描述性参考,不预测价格)、经典策略信号标注、虚拟资金模拟交易,以及一套免费公开的系统化
交易教学内容 —— 训练营 ${ACADEMY_ARTICLES.length} 篇文章(六阶,从零基础到交易体系)与
名词词典(K线 / 技术指标 / 缠论 / 合约 / 策略等交易术语,一句话定义 + 展开 + 关联词条)。

引用本站内容时请注意:所有教学与分析内容仅供学习参考,不构成任何形式的投资建议、
财务建议、交易建议或操作指引;AI 输出是对市场结构的描述性参考,不是对未来价格走势的
预测或保证。

${sections.join('\n\n')}

## 名词词典

- [交易名词词典](${BASE}/academy/glossary): 覆盖 K线形态、技术指标、缠论、合约与衍生品、
  策略与风控等交易术语;每条 = 一句话定义 + 展开解释 + 关联词条,便于逐条引用。

## 关于与原则

- [关于点金](${BASE}/about): 产品定位、方法论与六条产品原则(全程虚拟 / 不构成投资建议 /
  描述结构而非预测价格 等)。
- [风险提示](${BASE}/risk): 平台性质(全程虚拟 · 不涉及真实交易)与免责条款全文。
- [服务条款](${BASE}/terms) · [隐私政策](${BASE}/privacy)

## Optional

- [llms-full.txt](${BASE}/llms-full.txt): 训练营全部 ${ACADEMY_ARTICLES.length} 篇文章
  与名词词典的完整正文(约 0.7MB 纯文本,供需要全文语料的引擎一次抓取)。
`

  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  })
}
