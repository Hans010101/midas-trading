/**
 * 官网截图占位(官网刀1)· Hans 生产环境截图后刀2 替换为 <Image>。
 *
 * aspect 框 + 斜纹底 + 居中"界面预览"水印 · 与正式截图同尺寸语义(防替换跳版)。
 */

interface ScreenshotPlaceholderProps {
  /** 与未来截图一致的宽高比,如 'aspect-[16/10]' / 'aspect-[4/3]' */
  aspect: string
  /** 水印下方一行小字,说明这里将是什么截图 */
  label: string
}

export function ScreenshotPlaceholder({ aspect, label }: ScreenshotPlaceholderProps) {
  return (
    <div
      className={`relative ${aspect} overflow-hidden rounded-xl border border-paper bg-surface-subtle shadow-lg`}
    >
      {/* 斜纹底纹 · 纯 CSS 渐变,零资源 */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            'repeating-linear-gradient(45deg, #C8102E 0, #C8102E 1px, transparent 1px, transparent 12px)',
        }}
      />
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5">
        <span className="font-serif text-lg font-bold text-muted-foreground/40">界面预览</span>
        <span className="px-6 text-center text-xs text-muted-foreground/50">{label}</span>
      </div>
    </div>
  )
}
