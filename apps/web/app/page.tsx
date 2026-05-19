import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { VirtualBadge } from '@/components/ui/virtual-badge'

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-background gap-10 p-8">
      <div className="text-center space-y-3">
        <h1 className="font-serif text-5xl font-bold text-foreground">
          点金 <span className="text-midas-red">Midas</span>
        </h1>
        <p className="text-base text-muted-foreground">
          面向 A 股 / 美股 / 加密的 AI 原生分析终端
        </p>
        <p className="text-sm text-muted-foreground/70">
          模拟交易,不构成投资建议
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-4">
        <Button size="lg">立即体验</Button>
        <Badge>M0 · Checkpoint C</Badge>
        <VirtualBadge size="md" />
      </div>
    </main>
  )
}
