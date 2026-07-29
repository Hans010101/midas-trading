'use client'

/**
 * 训练营 markdown 渲染器 · react-markdown + remark-gfm(支持 GFM 表格,如 A11 现货/合约对比表)。
 *
 * 贴合项目设计语言:中国红 #C8102E 标题 / 暖金 gold 强调 / 宣纸白底 / Noto Serif SC 衬线标题 /
 * 中文排版(行高 1.85 · 段间距)。移动端:图片自适应、表格横向可滚动。
 * 入参 markdown 为原始字符串(由 server 端 lib/academy 用 fs 读出后传入)。
 */

import Image from 'next/image'
import Link from 'next/link'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { type PluggableList } from 'unified'

import { glossaryAnchorId, reactChildrenToText } from '@/lib/academy-anchor'
import { ACADEMY_IMG_DIMS } from '@/lib/academy-img-dims'
import { DEFAULT_EXCLUDE_TERMS, type AliasEntry } from '@/lib/glossary-terms'
import { rehypeGlossaryLinks } from '@/lib/rehype-glossary-links'

const components: Components = {
  // h1 = 文章主标题(md 首行 · 中国红 · 大)
  h1: ({ children }) => (
    <h1 className="mb-6 mt-1 font-serif text-2xl font-bold leading-snug text-midas-red lg:text-[1.75rem]">
      {children}
    </h1>
  ),
  // h2 = 小节标题(左红竖线)
  h2: ({ children }) => (
    <h2 className="mb-3 mt-9 border-l-4 border-midas-red pl-3 font-serif text-xl font-bold text-foreground">
      {children}
    </h2>
  ),
  // h3 = 暖金小标题 · 词典词条标题(`### N. 术语名`)额外输出锚点 id(术语名生成 · 不含序号)
  h3: ({ children }) => {
    const id = glossaryAnchorId(reactChildrenToText(children)) ?? undefined
    return (
      <h3
        id={id}
        className="mb-2 mt-6 scroll-mt-24 font-serif text-base font-bold text-gold"
      >
        {children}
      </h3>
    )
  },
  p: ({ children }) => <p className="my-4 leading-[1.85] text-foreground/85">{children}</p>,
  ul: ({ children }) => (
    <ul className="my-4 ml-5 list-disc space-y-2 leading-[1.85] text-foreground/85 marker:text-midas-red/60">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="my-4 ml-5 list-decimal space-y-2 leading-[1.85] text-foreground/85 marker:text-midas-red/60">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="pl-1">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  // a = 链接 · 站内链(如 [中枢](/academy/glossary#中枢))走 Next <Link> 软导航(不整页刷新);
  //     站外链(http)新开页。词典锚点定位由 glossary 页的 HashScroller 兜底。
  a: ({ href, children }) => {
    const h = typeof href === 'string' ? href : ''
    const className = 'text-midas-red underline-offset-2 hover:underline'
    if (h.startsWith('http')) {
      return (
        <a href={h} className={className} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      )
    }
    if (h.startsWith('/')) {
      return (
        <Link href={h} className={className}>
          {children}
        </Link>
      )
    }
    // 兜底(如纯 #hash 或空):原生 a
    return (
      <a href={h || undefined} className={className}>
        {children}
      </a>
    )
  },
  // blockquote = 模块标注(左暖金竖线 + 灰斜体)
  blockquote: ({ children }) => (
    <blockquote className="my-5 border-l-4 border-gold/70 bg-surface-subtle/60 py-2 pl-4 pr-3 italic text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-8 border-paper" />,
  // table = 带边框表格(th 暖金底)· 外层 overflow-x-auto 让移动端横向滚动
  table: ({ children }) => (
    <div className="my-5 overflow-x-auto">
      <table className="w-full min-w-[28rem] border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-paper bg-gold/15 px-3 py-2 text-left font-semibold text-foreground">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-paper px-3 py-2 align-top leading-relaxed text-foreground/85">
      {children}
    </td>
  ),
  // img = 居中 / 圆角 / 最大宽度 100%(md 图 path 已是 /academy-img/xxx.png → public 根)。
  // SEO webp 小刀:走 next/image 优化器 → 自动 webp/avif(实测单图 166KB→8.8KB · 省 ~95%),
  // 顺带吃 next.config images.minimumCacheTTL 31 天缓存。next/image 必须知 w/h 防抖动/失真,
  // 从预生成清单 academy-img-dims 查表(scripts/gen-academy-img-dims.mjs 生成);
  // 清单未收录的图(未来新增未重跑脚本)→ 裸 <img> 兜底,保证不破。lazy 是 next/image 默认。
  img: ({ src, alt }) => {
    const raw = typeof src === 'string' ? src : undefined
    // react-markdown 按 CommonMark 规范把非 ASCII src 百分号编码(中文图名 → %E9..%),
    // 而清单 key 与 next/image src 都要【解码后】的原始路径 → 统一解码(解码失败退回原值)。
    let s = raw
    if (raw) {
      try {
        s = decodeURIComponent(raw)
      } catch {
        s = raw
      }
    }
    const dim = s ? ACADEMY_IMG_DIMS[s] : undefined
    const className =
      'mx-auto my-5 block h-auto max-w-full rounded-lg border border-paper shadow-sm'
    if (s && dim) {
      return (
        <Image
          src={s}
          alt={alt ?? ''}
          width={dim.w}
          height={dim.h}
          sizes="(max-width: 1024px) 100vw, 720px"
          className={className}
        />
      )
    }
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={s} alt={alt ?? ''} loading="lazy" className={className} />
  },
  code: ({ children }) => (
    <code className="rounded bg-surface-subtle px-1.5 py-0.5 font-mono text-[0.85em] text-midas-red">
      {children}
    </code>
  ),
}

export function ArticleRenderer({
  markdown,
  glossaryAliases,
  locale = 'zh',
}: {
  markdown: string
  glossaryAliases?: AliasEntry[]
  locale?: 'zh' | 'en'
}) {
  const rehypePlugins: PluggableList =
    glossaryAliases && glossaryAliases.length > 0
      ? [[rehypeGlossaryLinks, { sortedAliases: glossaryAliases, exclude: DEFAULT_EXCLUDE_TERMS }]]
      : []
  return (
    <div className={locale === 'en' ? 'text-[15px] [&_p]:leading-7 [&_li]:leading-7' : undefined}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={rehypePlugins} components={components}>
        {markdown}
      </ReactMarkdown>
    </div>
  )
}
