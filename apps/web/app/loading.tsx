export default function Loading() {
  return (
    <main className="flex min-h-[70vh] items-center justify-center bg-background px-4 text-foreground">
      <div role="status" className="w-full max-w-sm rounded-xl border border-paper bg-cream p-6 shadow-sm">
        <div className="mb-5 h-5 w-32 animate-pulse rounded bg-paper" />
        <div className="space-y-3">
          <div className="h-3 animate-pulse rounded bg-paper/80" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-paper/70" />
          <div className="h-24 animate-pulse rounded-lg bg-paper/60" />
        </div>
        <p className="mt-4 text-center text-xs text-muted-foreground">正在载入 / Loading…</p>
      </div>
    </main>
  )
}
