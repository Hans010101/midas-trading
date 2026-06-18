'use client'

/**
 * 训练营 markdown 渲染器 · react-markdown + remark-gfm(支持 GFM 表格,如 A11 现货/合约对比表)。
 *
 * 贴合项目设计语言:中国红 #C8102E 标题 / 暖金 gold 强调 / 宣纸白底 / Noto Serif SC 衬线标题 /
 * 中文排版(行高 1.85 · 段间距)。移动端:图片自适应、表格横向可滚动。
 * 入参 markdown 为原始字符串(由 server 端 lib/academy 用 fs 读出后传入)。
 */

import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

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
  // h3 = 暖金小标题
  h3: ({ children }) => (
    <h3 className="mb-2 mt-6 font-serif text-base font-bold text-gold">{children}</h3>
  ),
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
  a: ({ href, children }) => {
    const external = typeof href === 'string' && href.startsWith('http')
    return (
      <a
        href={href}
        className="text-midas-red underline-offset-2 hover:underline"
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
      >
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
  // img = 居中 / 圆角 / 最大宽度 100% / 懒加载(md 图 path 已是 /academy-img/xxx.png → public 根)
  img: ({ src, alt }) => (
    // markdown 内容图无固定尺寸,next/image 需 fill+容器不适用 → 用原生 img + lazy
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={typeof src === 'string' ? src : undefined}
      alt={alt ?? ''}
      loading="lazy"
      className="mx-auto my-5 block max-w-full rounded-lg border border-paper shadow-sm"
    />
  ),
  code: ({ children }) => (
    <code className="rounded bg-surface-subtle px-1.5 py-0.5 font-mono text-[0.85em] text-midas-red">
      {children}
    </code>
  ),
}

export function ArticleRenderer({ markdown }: { markdown: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {markdown}
    </ReactMarkdown>
  )
}
