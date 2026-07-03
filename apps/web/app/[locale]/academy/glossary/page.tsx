/**
 * 名词词典页 · server component(fs 读 glossary.md → ArticleRenderer 渲染)。
 *
 * 词典本身是结构化 markdown(含目录 + 10 大类 + 88 条 · 每条一句话定义 + 展开 + 关联词条),
 * 直接整篇渲染即可(目录里的锚点跳转随 md 渲染天然生效)。全免费,无门控。
 *
 * UI 修补:删二级标签行,改为常驻左侧导航 AcademySideNav(active='glossary' · 词典项高亮)。
 */

import { AcademySideNav } from '@/components/academy/academy-side-nav'
import { ArticleRenderer } from '@/components/academy/article-renderer'
import { HashScroller } from '@/components/academy/hash-scroller'
import { TopNav } from '@/components/layout/top-nav'
import { getGlossary } from '@/lib/academy'

export default function AcademyGlossaryPage() {
  const markdown = getGlossary()

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      {/* 到达 /academy/glossary#<术语id> 时滚动定位到对应词条(软导航/直接访问都兜底)*/}
      <HashScroller />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          <div className="lg:flex lg:gap-8">
            <AcademySideNav active="glossary" />
            <div className="min-w-0 flex-1">
              <ArticleRenderer markdown={markdown} />
              <p className="mt-8 border-t border-paper pt-4 text-xs text-muted-foreground/60">
                教学内容,仅供学习参考,不构成投资建议。
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
