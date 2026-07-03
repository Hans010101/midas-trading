/**
 * 用户中心嵌套 layout(重组刀1)· TopNav + 四模块导航(lg 侧栏 / 移动顶部 tab)。
 *
 * 子页只渲染内容本体(不再各自带 TopNav / main 容器)。
 */

import { AccountNav } from '@/components/account/account-nav'
import { TopNav } from '@/components/layout/top-nav'

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="lg:flex lg:gap-8">
          <AccountNav />
          <div className="min-w-0 flex-1">{children}</div>
        </div>
      </main>
    </div>
  )
}
