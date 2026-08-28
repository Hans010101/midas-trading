import Link from 'next/link'

export default function NotFound() {
  return (
    <main className="flex min-h-[70vh] items-center justify-center bg-background px-4 text-foreground">
      <div className="max-w-md rounded-xl border border-paper bg-cream p-7 text-center shadow-sm">
        <p className="font-mono text-xs text-midas-red">404</p>
        <h1 className="mt-2 font-serif text-xl font-bold">页面不存在 / Page not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">链接可能已更新，请从四市场总览继续。</p>
        <Link
          href="/global"
          className="mt-5 inline-flex rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          返回全球市场 / Global markets
        </Link>
      </div>
    </main>
  )
}
