/** 铂金自助页共享展示组件(StatCard + 分页)· 智能/托管两面板共用。 */

export function StatCard({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-3 shadow-sm">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-lg font-bold ${tone ?? 'text-foreground'}`}>{value}</div>
    </div>
  )
}

export function Pagination({
  page,
  pages,
  isFetching,
  onPrev,
  onNext,
}: {
  page: number
  pages: number
  isFetching: boolean
  onPrev: () => void
  onNext: () => void
}) {
  return (
    <div className="mt-3 flex items-center justify-center gap-3 text-xs">
      <button
        type="button"
        onClick={onPrev}
        disabled={page <= 0 || isFetching}
        className="rounded-md border border-paper px-3 py-1 text-muted-foreground hover:text-foreground disabled:opacity-40"
      >
        上一页
      </button>
      <span className="font-mono text-muted-foreground">
        第 {page + 1} / {pages} 页
      </span>
      <button
        type="button"
        onClick={onNext}
        disabled={page >= pages - 1 || isFetching}
        className="rounded-md border border-paper px-3 py-1 text-muted-foreground hover:text-foreground disabled:opacity-40"
      >
        下一页
      </button>
    </div>
  )
}
