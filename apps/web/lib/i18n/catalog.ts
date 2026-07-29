import type { Locale } from '@/i18n/routing'

export type MessageTree = Readonly<Record<string, unknown>>

type CatalogEntry = Readonly<{
  key: string
  source: string
  target: string
}>

type TemplateEntry = Readonly<{
  pattern: RegExp
  render: (match: RegExpMatchArray) => string
}>

export type TranslationCatalog = Readonly<{
  exact: ReadonlyMap<string, string>
  canonical: ReadonlyMap<string, string>
  templates: readonly TemplateEntry[]
}>

const NAMESPACE_PRIORITY = [
  'common',
  'runtime',
  'admin',
  'landing',
  'market',
  'workbench',
  'settings',
  'screener',
  'academy',
  'backendLabels',
  'backendErrors',
] as const

function flattenMessages(
  tree: MessageTree,
  prefix = '',
  result: Map<string, string> = new Map(),
): Map<string, string> {
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') {
      result.set(path, value)
    } else if (value && typeof value === 'object' && !Array.isArray(value)) {
      flattenMessages(value as MessageTree, path, result)
    }
  }
  return result
}

function priority(key: string): number {
  const namespace = key.split('.')[0]
  const index = NAMESPACE_PRIORITY.indexOf(
    namespace as (typeof NAMESPACE_PRIORITY)[number],
  )
  return index === -1 ? NAMESPACE_PRIORITY.length : index
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function canonicalize(value: string): string {
  return value.replace(/\s+/gu, '')
}

function compileTemplate(source: string, target: string): TemplateEntry | null {
  const tokenPattern = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g
  const sourceTokens = [...source.matchAll(tokenPattern)]
  if (sourceTokens.length === 0) return null

  // ICU plural/select expressions contain nested punctuation and are handled by
  // next-intl components directly. The bridge only supports simple placeholders.
  const braceCount = (source.match(/\{/g) ?? []).length
  if (braceCount !== sourceTokens.length) return null

  let cursor = 0
  let expression = '^'
  const captureByName = new Map<string, number>()
  for (const token of sourceTokens) {
    const index = token.index ?? 0
    expression += escapeRegExp(source.slice(cursor, index))
    const name = token[1]
    const existing = captureByName.get(name)
    if (existing) {
      expression += `\\${existing}`
    } else {
      captureByName.set(name, captureByName.size + 1)
      expression += '(.+?)'
    }
    cursor = index + token[0].length
  }
  expression += `${escapeRegExp(source.slice(cursor))}$`

  return {
    pattern: new RegExp(expression, 'u'),
    render(match) {
      return target.replace(tokenPattern, (_token, name: string) => {
        const capture = captureByName.get(name)
        return capture ? (match[capture] ?? '') : ''
      })
    },
  }
}

export function buildTranslationCatalog(
  zhMessages: MessageTree,
  enMessages: MessageTree,
): TranslationCatalog {
  const zh = flattenMessages(zhMessages)
  const en = flattenMessages(enMessages)
  const entries: CatalogEntry[] = []

  for (const [key, source] of zh) {
    const target = en.get(key)
    if (!target || target === source) continue
    entries.push({ key, source: source.trim(), target: target.trim() })
  }

  entries.sort((a, b) => priority(a.key) - priority(b.key))
  const exact = new Map<string, string>()
  const canonical = new Map<string, string>()
  const templates: TemplateEntry[] = []

  for (const entry of entries) {
    if (!entry.source || exact.has(entry.source)) continue
    const template = compileTemplate(entry.source, entry.target)
    if (template) {
      templates.push(template)
    } else {
      exact.set(entry.source, entry.target)
      const normalized = canonicalize(entry.source)
      if (!canonical.has(normalized)) canonical.set(normalized, entry.target)
    }
  }

  return { exact, canonical, templates }
}

export function translateCatalogText(
  value: string,
  locale: Locale,
  catalog: TranslationCatalog,
): string {
  if (locale === 'zh' || !/[\u3400-\u9fff]/u.test(value)) return value

  const leading = value.match(/^\s*/u)?.[0] ?? ''
  const trailing = value.match(/\s*$/u)?.[0] ?? ''
  const core = value.slice(leading.length, value.length - trailing.length)
  const exact = catalog.exact.get(core)
  if (exact) return `${leading}${exact}${trailing}`
  const canonical = catalog.canonical.get(canonicalize(core))
  if (canonical) return `${leading}${canonical}${trailing}`

  for (const template of catalog.templates) {
    const match = core.match(template.pattern)
    if (match) {
      let rendered = template.render(match)
      // A placeholder can itself be a registered interface label, such as
      // "{label} 左移" with "布林做T". Translate those embedded labels too.
      if (/[\u3400-\u9fff]/u.test(rendered)) {
        for (const [source, target] of catalog.exact) {
          if (
            /[\u3400-\u9fff]/u.test(source) &&
            rendered.includes(source)
          ) {
            rendered = rendered.replaceAll(source, target)
          }
        }
      }
      return `${leading}${rendered}${trailing}`
    }
  }
  return value
}
