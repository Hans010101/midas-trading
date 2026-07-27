/**
 * 法律静态页骨架(服务条款 / 隐私政策 / 风险提示 共用)· 纯静态展示,不依赖后端/登录。
 *
 * Logo 头(返回首页)+ max-w-3xl 居中正文(移动端友好)+ 独立项目客服入口说明。
 * 复用官网设计语言(背景/字色/衬线标题)。
 */

import Image from 'next/image'
import Link from 'next/link'

export function LegalPage({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b border-paper/80 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/brand/seal.png" alt="点金 Midas 印章" width={32} height={32} />
            <span className="font-serif text-lg font-bold text-midas-red">Midas</span>
          </Link>
          <Link
            href="/"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            返回首页
          </Link>
        </div>
      </header>

      <article className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="mb-8 font-serif text-3xl font-bold">{title}</h1>
        <div className="space-y-4 text-sm leading-relaxed text-foreground/85">{children}</div>
      </article>

      <footer className="border-t border-paper bg-surface-card">
        <div className="mx-auto max-w-3xl px-6 py-6 text-xs text-muted-foreground">
          <p>客服:请登录后通过站内“联系我们”提交工单</p>
          <p className="mt-1">© 2026 Midas Trading · 仅供模拟交易,不构成投资建议</p>
        </div>
      </footer>
    </main>
  )
}

/** 一级标题(如「一、xxx」)· 加粗衬线。 */
export function LegalH2({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-8 font-serif text-lg font-bold text-foreground">{children}</h2>
}

/** 正文段落。 */
export function LegalP({ children }: { children: React.ReactNode }) {
  return <p className="leading-relaxed text-foreground/85">{children}</p>
}

/** 项目符号列表。 */
export function LegalUL({ children }: { children: React.ReactNode }) {
  return <ul className="ml-5 list-disc space-y-1 text-foreground/85">{children}</ul>
}
