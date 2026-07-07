/**
 * 访问埋点 beacon 判定纯函数(从 middleware 抽出 · 可单测 · 不引 NextAuth)。
 *
 * 两个 P0 修复的判定逻辑都在这:
 *  - Bug A(来源污染):extractRefHost 用【正确的自有域】剔除站内跳转 —— 自有域来自
 *    调用方传入的 Host 头(Caddy `header_up Host {host}` 正确透传 apex),不用 nextUrl.hostname
 *    (standalone 部署下常是 localhost/内网 → 自指判断失效 → 站内跳转被误记成 referral)。
 *  - Bug B(PV 虚高):isPrefetchRequest 认 Next 15 的预取请求 → 中间件据此跳过 PV beacon。
 *    ★只排除【预取】(speculative · 未真浏览);真软导航(点击)不带预取头 → 照常计 PV。
 */

// 已知爬虫 / 预览抓取 / 监控 / 脚本 UA → 不计入人类 PV(与 classifyCrawler 的独立 GEO 计数分离)。
export const BOT_RE =
  /bot|crawl|spider|slurp|bing|baidu|yandex|duckduck|facebookexternalhit|embedly|quora|pinterest|slackbot|telegram|whatsapp|headless|lighthouse|monitor|uptime|pingdom|curl|wget|python-requests|go-http|axios|okhttp|java\//i

// SEO 批6:AI/搜索爬虫 UA 分类(GEO 领先指标)· 有序:先 AI 再搜索(前缀 search:)· 返回桶名或 null。
const CRAWLER_UA: ReadonlyArray<readonly [RegExp, string]> = [
  [/gptbot/i, 'GPTBot'],
  [/oai-searchbot/i, 'OAI-SearchBot'],
  [/chatgpt-user/i, 'ChatGPT-User'],
  [/claudebot/i, 'ClaudeBot'],
  [/claude-web/i, 'Claude-Web'],
  [/anthropic-ai/i, 'anthropic-ai'],
  [/perplexitybot/i, 'PerplexityBot'],
  [/perplexity-user/i, 'Perplexity-User'],
  [/google-extended/i, 'Google-Extended'],
  [/applebot-extended/i, 'Applebot-Extended'],
  [/bytespider/i, 'Bytespider'],
  [/ccbot/i, 'CCBot'],
  [/cohere-ai/i, 'cohere-ai'],
  [/meta-externalagent/i, 'Meta-ExternalAgent'],
  [/amazonbot/i, 'Amazonbot'],
  [/youbot/i, 'YouBot'],
  [/diffbot/i, 'Diffbot'],
  [/googlebot/i, 'search:Googlebot'],
  [/bingbot/i, 'search:Bingbot'],
  [/baiduspider/i, 'search:Baiduspider'],
  [/yandexbot/i, 'search:YandexBot'],
  [/duckduckbot/i, 'search:DuckDuckBot'],
]

export function classifyCrawler(ua: string): string | null {
  for (const [re, name] of CRAWLER_UA) {
    if (re.test(ua)) return name
  }
  return null
}

/** host 归一:小写 · 去端口 · 去 www. 前缀(自指比较两侧对称化,避免 apex/www 不对称漏判)。 */
export function normalizeHost(h: string): string {
  const lower = h.trim().toLowerCase().split(':')[0]
  return lower.startsWith('www.') ? lower.slice(4) : lower
}

/**
 * referrer → 来源域名 host(剥 path/query · 归一)。
 * ★同域(站内跳转)或无 referrer → null(不上报,不算外部来源)。
 * @param selfHost 当前请求的真实公网 host —— 调用方传 req.headers.get('host')(Caddy 透传),
 *   ★不要传 req.nextUrl.hostname(standalone 下 = 内网 host,自指判断会失效)。
 */
export function extractRefHost(referer: string | null, selfHost: string | null): string | null {
  if (!referer) return null
  try {
    const h = normalizeHost(new URL(referer).hostname)
    if (!h) return null
    const self = selfHost ? normalizeHost(selfHost) : ''
    if (self && h === self) return null // 站内跳转不算来源
    return h.slice(0, 120)
  } catch {
    return null
  }
}

/**
 * 是否 Next 15 的【预取 / 推测加载】请求(不是真实页面浏览)。
 * 依据 Next 源码 app-router-headers.js + fetch-server-response.js:
 *  - next-router-prefetch:AUTO 预取(默认 <Link> 视口预取)会设 '1' · 正常导航(点击)不带。
 *  - next-router-segment-prefetch:分段/PPR 预取。
 *  - sec-purpose 含 prefetch:浏览器级推测加载(Speculation Rules / <link rel=prefetch>)。
 * ★真软导航(点击)不带以上任何头 → isPrefetchRequest=false → 照常计 PV。
 */
export function isPrefetchRequest(headers: Headers): boolean {
  if (headers.get('next-router-prefetch') != null) return true
  if (headers.get('next-router-segment-prefetch') != null) return true
  const secPurpose = headers.get('sec-purpose')
  if (secPurpose && secPurpose.toLowerCase().includes('prefetch')) return true
  return false
}
