import Image from 'next/image'
import Link from 'next/link'

export function PublicSiteShell({
  children,
  english = false,
}: {
  children: React.ReactNode
  english?: boolean
}) {
  const prefix = english ? '/en' : ''
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-paper bg-background/95">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
          <Link href={prefix || '/'} className="flex items-center gap-2">
            <Image src="/brand/seal.png" alt="Midas Trading" width={32} height={32} />
            <span className="font-serif text-lg font-bold text-midas-red">Midas Trading</span>
          </Link>
          <nav className="flex items-center gap-5 text-sm text-muted-foreground">
            <Link href={`${prefix}/academy`} className="hover:text-midas-red">
              {english ? 'Academy' : '训练营'}
            </Link>
            <Link href={`${prefix}/research/methodology`} className="hidden hover:text-midas-red sm:inline">
              {english ? 'Methodology' : '研究方法'}
            </Link>
            <Link href={english ? '/' : '/en'} className="hover:text-midas-red">
              {english ? '中文' : 'English'}
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
      <footer className="mt-12 border-t border-paper bg-surface-card">
        <div className="mx-auto flex max-w-5xl flex-wrap gap-x-6 gap-y-2 px-6 py-6 text-xs text-muted-foreground">
          <span>© 2026 Midas Trading</span>
          <Link href={`${prefix}/about`} className="hover:text-midas-red">
            {english ? 'About' : '关于'}
          </Link>
          <Link href={`${prefix}/research/methodology`} className="hover:text-midas-red">
            {english ? 'Methodology' : '研究方法'}
          </Link>
          <Link href={`${prefix}/research/team`} className="hover:text-midas-red">
            {english ? 'Research team' : '研究团队'}
          </Link>
          <Link href={`${prefix}/academy/glossary`} className="hover:text-midas-red">
            {english ? 'Glossary' : '交易词典'}
          </Link>
          <Link href={`${prefix}/terms`} className="hover:text-midas-red">
            {english ? 'Terms' : '服务条款'}
          </Link>
          <Link href={`${prefix}/privacy`} className="hover:text-midas-red">
            {english ? 'Privacy' : '隐私政策'}
          </Link>
          <Link href={`${prefix}/risk`} className="hover:text-midas-red">
            {english ? 'Risk notice' : '风险提示'}
          </Link>
          <Link href={`${prefix}/refund`} className="hover:text-midas-red">
            {english ? 'Free service' : '免费服务'}
          </Link>
        </div>
      </footer>
    </div>
  )
}

export function PublicProse({ children }: { children: React.ReactNode }) {
  return <article className="mx-auto max-w-3xl space-y-5 text-[15px] leading-7">{children}</article>
}
