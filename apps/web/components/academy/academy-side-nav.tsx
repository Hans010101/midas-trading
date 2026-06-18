/**
 * 训练营左侧导航 · 文章列表页 / 文章详情页 / 词典页常驻(首页不用)。
 *
 * 范式照 components/account/account-nav.tsx(同款 token,一个组件按断点两种渲染):
 *   lg+   → 左侧竖栏(当前项中国红高亮 + 左边线)
 *   lg 以下 → 顶部水平 scrollable tab(framed-segment · 窄屏可横滚)
 *
 * 6 项 = 5 阶(★从 manifest ACADEMY_STAGES 读 · 不硬编码中文名/顺序)+ 名词词典。
 * active:当前项 key(stage slug 或 'glossary')· 由各页传入。
 * 纯展示、无 hooks → server / client 父组件均可用(文章/词典页是 server,列表页是 client)。
 */

import Link from 'next/link'

import { ACADEMY_STAGES } from '@/content/academy/manifest'
import { cn } from '@/lib/utils'

const GLOSSARY_KEY = 'glossary'

function navItems() {
  return [
    ...ACADEMY_STAGES.map((s) => ({
      key: s.slug,
      href: `/academy/stage?s=${s.slug}`,
      label: `${s.stageLabel} ${s.name}`,
    })),
    { key: GLOSSARY_KEY, href: '/academy/glossary', label: '名词词典' },
  ]
}

export function AcademySideNav({ active }: { active: string }) {
  const items = navItems()
  return (
    <>
      {/* lg+ 左侧栏 */}
      <nav className="hidden w-48 shrink-0 lg:block" aria-label="训练营导航">
        <ul className="space-y-1">
          {items.map((item) => (
            <li key={item.key}>
              <Link
                href={item.href}
                className={cn(
                  'block rounded-md border-l-2 px-3 py-2 text-sm transition-colors',
                  item.key === active
                    ? 'border-midas-red bg-midas-red-glow font-medium text-midas-red'
                    : 'border-transparent text-muted-foreground hover:bg-cream hover:text-foreground',
                )}
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      {/* lg 以下 顶部水平 tab(framed-segment · 窄屏可横滚) */}
      <div className="mb-6 overflow-x-auto lg:hidden">
        <div className="flex w-max min-w-full overflow-hidden rounded-md border border-paper text-sm">
          {items.map((item) => (
            <Link
              key={item.key}
              href={item.href}
              className={cn(
                'whitespace-nowrap px-4 py-1.5 transition-colors',
                item.key === active
                  ? 'bg-midas-red text-white'
                  : 'text-muted-foreground hover:bg-midas-red-glow/50',
              )}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </div>
    </>
  )
}
