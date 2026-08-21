import { PRODUCTION_WEB_URL } from '@/lib/site'

const PRIVATE_PATHS = ['/account', '/settings', '/portfolio', '/dashboard', '/admin', '/api/']
const TRAINING_CRAWLERS = [
  'Amazonbot',
  'Applebot-Extended',
  'Bytespider',
  'CCBot',
  'ClaudeBot',
  'Google-Extended',
  'GPTBot',
  'meta-externalagent',
]

export function GET() {
  const privateRules = PRIVATE_PATHS.map((path) => `Disallow: ${path}`).join('\n')
  const trainingRules = TRAINING_CRAWLERS.map(
    (crawler) => `User-agent: ${crawler}\nDisallow: /`,
  ).join('\n\n')

  return new Response(
    `User-agent: *\nContent-signal: search=yes, ai-input=yes, ai-train=no, use=reference\nAllow: /\n${privateRules}\n\n${trainingRules}\n\nSitemap: ${PRODUCTION_WEB_URL}/sitemap.xml\n`,
    { headers: { 'content-type': 'text/plain; charset=utf-8' } },
  )
}
