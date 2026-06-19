'use client'

/**
 * 训练营随堂小测 · 训练营第一个交互组件(client · React state · 无后端)。
 *
 * 渲染某篇文章的题目(由 server 端 app/academy/article/page.tsx 从 content/academy/quizzes.ts
 * 按 slug 取出后作为 prop 传入)。交互:点选项 → 即时比对 answerIndex → 高亮对 / 错 +
 * 永远标出正确项 + 展示解析。每题独立、可重答(再点别的选项即重判)。
 *
 * 视觉沿用训练营:中国红强调 / 暖米白卡片 / Noto Serif 标题 / success 绿表「答对」
 * (success 与涨跌 up/down 解耦,不随偏好开关翻转 · tailwind.config.ts:81)。
 * 无题(questions 为空)→ 返回 null,不渲染该区。
 */

import { CheckCircle2, ListChecks, XCircle } from 'lucide-react'
import { useState } from 'react'

import type { QuizQuestion } from '@/content/academy/quizzes'
import { cn } from '@/lib/utils'

/** 选项序号 → A / B / C / D */
function optionLabel(index: number): string {
  return String.fromCharCode(65 + index)
}

export function ArticleQuiz({ questions }: { questions: QuizQuestion[] }) {
  // 每题选中的选项下标(题序 → 选项序);未答的题不在 map 中
  const [picked, setPicked] = useState<Record<number, number>>({})

  if (questions.length === 0) return null

  return (
    <section className="mt-12 border-t border-paper pt-8" aria-label="随堂小测">
      <h2 className="mb-1 flex items-center gap-2 font-serif text-xl font-bold text-foreground">
        <ListChecks className="h-5 w-5 text-midas-red" />
        随堂小测
      </h2>
      <p className="mb-5 text-sm text-muted-foreground">
        共 {questions.length} 题 · 点选项即时查看对错与解析,可重答。
      </p>

      <div className="space-y-5">
        {questions.map((q, qi) => {
          const chosen = picked[qi]
          const answered = chosen !== undefined
          const isRight = answered && chosen === q.answerIndex
          return (
            <div
              key={qi}
              className="rounded-xl border border-paper bg-cream p-4 shadow-sm sm:p-5"
            >
              {/* 题干 */}
              <div className="flex gap-2.5">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-midas-red/10 font-mono text-xs text-midas-red">
                  {qi + 1}
                </span>
                <p className="font-medium leading-relaxed text-foreground">{q.stem}</p>
              </div>

              {/* 选项 */}
              <ul className="mt-3 space-y-2">
                {q.options.map((opt, oi) => {
                  const isChosen = chosen === oi
                  const isCorrect = oi === q.answerIndex
                  const showCorrect = answered && isCorrect
                  const showWrong = answered && isChosen && !isCorrect
                  return (
                    <li key={oi}>
                      <button
                        type="button"
                        onClick={() => setPicked((prev) => ({ ...prev, [qi]: oi }))}
                        aria-pressed={isChosen}
                        className={cn(
                          'flex w-full items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors',
                          !answered &&
                            'border-paper bg-background hover:border-midas-red/40 hover:bg-midas-red-glow',
                          showCorrect && 'border-success bg-success/10 text-success',
                          showWrong && 'border-midas-red bg-midas-red/10 text-midas-red',
                          answered &&
                            !showCorrect &&
                            !showWrong &&
                            'border-paper bg-background/50 text-muted-foreground',
                        )}
                      >
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center font-mono text-xs">
                          {showCorrect ? (
                            <CheckCircle2 className="h-4 w-4" />
                          ) : showWrong ? (
                            <XCircle className="h-4 w-4" />
                          ) : (
                            optionLabel(oi)
                          )}
                        </span>
                        <span className="flex-1">{opt}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>

              {/* 反馈 + 解析 */}
              {answered && (
                <div
                  className={cn(
                    'mt-3 rounded-lg border px-3 py-2.5 text-sm leading-relaxed text-foreground/80',
                    isRight ? 'border-success/30 bg-success/5' : 'border-midas-red/30 bg-midas-red/5',
                  )}
                >
                  <p
                    className={cn(
                      'mb-1 font-semibold',
                      isRight ? 'text-success' : 'text-midas-red',
                    )}
                  >
                    {isRight
                      ? '✓ 回答正确'
                      : `✗ 回答错误 · 正确答案 ${optionLabel(q.answerIndex)}`}
                  </p>
                  <p>{q.explanation}</p>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
