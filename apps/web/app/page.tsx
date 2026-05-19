import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
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
        <Tooltip>
          <TooltipTrigger asChild>
            {/* Radix Tooltip 在 disabled 按钮上不触发,用 span 承载 hover/keyboard;
                cursor-not-allowed 放 span(disabled 按钮自身 pointer-events:none,
                光标样式不生效),visual 上仍呈现禁用感。 */}
            <span tabIndex={0} className="inline-block cursor-not-allowed">
              <Button size="lg" disabled className="cursor-not-allowed">
                立即体验
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>M0 阶段未实装,Task 7.1 开放</TooltipContent>
        </Tooltip>
        <Badge>M0 · Checkpoint C</Badge>
        <VirtualBadge size="md" />
      </div>
    </main>
  )
}
