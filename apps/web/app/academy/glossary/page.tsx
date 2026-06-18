/**
 * 名词词典页 · server component(fs 读 glossary.md → ArticleRenderer 渲染)。
 *
 * 词典本身是结构化 markdown(含目录 + 8 大类 + 66 条 · 每条一句话定义 + 展开 + 关联词条),
 * 直接整篇渲染即可(目录里的锚点跳转随 md 渲染天然生效)。全免费,无门控。
 */

import { AcademyNav } from '@/components/academy/academy-nav'
import { ArticleRenderer } from '@/components/academy/article-renderer'
import { TopNav } from '@/components/layout/top-nav'
import { getGlossary } from '@/lib/academy'

export default function AcademyGlossaryPage() {
  const markdown = getGlossary()

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-3xl px-6 py-6">
          <AcademyNav />
          <ArticleRenderer markdown={markdown} />
          <p className="mt-8 border-t border-paper pt-4 text-xs text-muted-foreground/60">
            教学内容,仅供学习参考,不构成投资建议。
          </p>
        </div>
      </main>
    </div>
  )
}
