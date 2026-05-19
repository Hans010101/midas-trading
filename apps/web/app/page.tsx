export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-white">
      <div className="text-center">
        <h1 className="font-serif text-4xl font-bold text-ink">
          点金 <span className="text-midas-red">Midas</span>
        </h1>
        <p className="mt-4 text-ink-dim">
          面向 A 股 / 美股 / 加密的 AI 原生分析终端
        </p>
        <p className="mt-2 text-sm text-ink-faint">
          模拟交易，不构成投资建议
        </p>
      </div>
    </main>
  )
}
