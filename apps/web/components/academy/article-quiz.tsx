'use client'

/**
 * 训练营随堂小测 · 训练营第一个交互组件(client · React state)。
 *
 * 刀1.5 升级:
 * ① 选项前端运行时洗牌(Fisher-Yates · useState 惰性初始化【挂载洗一次】· 判定用洗牌后下标)
 *    —— 修正题库正确答案扎堆 B 位;题库数据零改;新增题自动享受打散。
 * ② 答完本篇所有题(每题都选过)→ 自动标记学完(复用刀1 POST /academy/progress/complete)·
 *    幂等(已完成/未登录/进行中不重复触发,见 shouldAutoMark)· 删手动按钮 · 保留「已学完」反馈。
 *
 * 视觉沿用训练营:中国红强调 / 暖米白卡片 / success 绿表「答对 / 已学完」(与涨跌解耦)。
 * 无题(questions 为空)→ 返回 null,不渲染该区(无小测文章不参与进度,见 academy-progress-calc)。
 */

import { CheckCircle2, ListChecks, XCircle } from 'lucide-react'
import Link from 'next/link'
import { useEffect, useState } from 'react'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import type { QuizQuestion } from '@/content/academy/quizzes'
import { useAcademyProgress, useMarkComplete } from '@/hooks/use-academy-progress'
import { shouldAutoMark } from '@/lib/academy-progress-calc'
import { shuffleQuestion } from '@/lib/quiz-shuffle'
import { cn } from '@/lib/utils'

/** 选项序号 → A / B / C / D */
function optionLabel(index: number): string {
  return String.fromCharCode(65 + index)
}

export function ArticleQuiz({ questions, slug }: { questions: QuizQuestion[]; slug: string }) {
  // ★ 挂载时洗一次(惰性初始化)· 不每次 render 重洗(否则选完选项跳位)。文章切换由父组件 key=slug 强制重挂。
  const [shuffled] = useState(() => questions.map((q) => shuffleQuestion(q)))
  // 每题选中的(洗牌后)选项下标;未答的题不在 map 中
  const [picked, setPicked] = useState<Record<number, number>>({})
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'

  const { completedSet, isLoggedIn } = useAcademyProgress()
  const mark = useMarkComplete()

  const allAnswered = questions.length > 0 && Object.keys(picked).length === questions.length
  const alreadyCompleted = completedSet.has(slug)

  // ② 答完所有题 → 自动标记学完(幂等判定见 shouldAutoMark · 已完成/未登录/进行中不触发)
  useEffect(() => {
    if (shouldAutoMark({ allAnswered, isLoggedIn, alreadyCompleted, isPending: mark.isPending })) {
      mark.mutate(slug)
    }
    // mark 故意不入依赖(其 isPending 在判定内读 · 入依赖会重复触发);仅 4 个真实条件变化时重算
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allAnswered, isLoggedIn, alreadyCompleted, slug])

  if (questions.length === 0) return null

  // 完成反馈:已登录且(已完成 OR 刚答完将被标记)→ 显示「已学完本篇」(乐观,标记请求在途也显)
  const showCompleted = isLoggedIn && (alreadyCompleted || allAnswered)
  // 未登录答完 → 引导登录(不强制 · 不报错)
  const showLoginHint = !isLoggedIn && allAnswered

  return (
    <section
      className="mt-12 border-t border-paper pt-8"
      aria-label={en ? 'Lesson quiz' : '随堂小测'}
    >
      <h2 className="mb-1 flex items-center gap-2 font-serif text-xl font-bold text-foreground">
        <ListChecks className="h-5 w-5 text-midas-red" />
        {en ? 'Check your understanding' : '随堂小测'}
      </h2>
      <p className="mb-5 text-sm text-muted-foreground">
        {en
          ? `${questions.length} questions · Select an answer for instant feedback. Complete all questions to record your progress.`
          : `共 ${questions.length} 题 · 点选项即时查看对错与解析,可重答;答完本篇自动记录学习进度。`}
      </p>

      <div className="space-y-5">
        {questions.map((q, qi) => {
          const sq = shuffled[qi] // 洗牌后的 options + answerIndex
          const chosen = picked[qi]
          const answered = chosen !== undefined
          const isRight = answered && chosen === sq.answerIndex
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

              {/* 选项(洗牌后顺序)*/}
              <ul className="mt-3 space-y-2">
                {sq.options.map((opt, oi) => {
                  const isChosen = chosen === oi
                  const isCorrect = oi === sq.answerIndex
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

              {/* 反馈 + 解析(正确答案用洗牌后下标)*/}
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
                      ? (en ? '✓ Correct' : '✓ 回答正确')
                      : (en
                          ? `✗ Not quite · Correct answer: ${optionLabel(sq.answerIndex)}`
                          : `✗ 回答错误 · 正确答案 ${optionLabel(sq.answerIndex)}`)}
                  </p>
                  <p>{q.explanation}</p>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 完成反馈 / 登录引导(替代刀1 的手动「标记学完」按钮)*/}
      {showCompleted && (
        <div className="mt-6 flex items-center gap-2 rounded-lg border border-success bg-success/10 px-4 py-3 text-sm font-medium text-success">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          {en ? 'Lesson complete · Progress saved' : '已学完本篇 · 学习进度已记录'}
        </div>
      )}
      {showLoginHint && (
        <div className="mt-6 flex items-center justify-between gap-3 rounded-lg border border-dashed border-paper bg-surface-subtle px-4 py-3">
          <span className="text-sm text-muted-foreground">
            {en ? 'Sign in to save your learning progress' : '登录后自动记录学习进度'}
          </span>
          <Link
            href="/login"
            className="shrink-0 rounded-md border border-midas-red/40 px-3 py-1.5 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow"
          >
            {en ? 'Sign in' : '去登录'}
          </Link>
        </div>
      )}
    </section>
  )
}
