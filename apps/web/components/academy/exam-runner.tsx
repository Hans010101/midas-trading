'use client'

/**
 * 模块结业测验 · 训练营 B 期刀2(client)。
 *
 * 流程:登录门 → 拉题(★无答案)→ 洗牌作答(刀1.5 复用 shuffleOptions)→ 提交(★映射回原序,
 * 后端判分)→ 显示得分/是否达标/解析 → 达标显结业金徽章 / 未达标可重考。
 * ★本刀只发结业荣誉,不发会员(发会员是刀3)· 成绩存后端(非 localStorage)。
 */

import { Award, CheckCircle2, ChevronRight, Home, RotateCcw, XCircle } from 'lucide-react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useMemo, useState } from 'react'

import { TopNav } from '@/components/layout/top-nav'
import { ACADEMY_STAGES } from '@/content/academy/manifest'
import { useExamQuestions, useExamResults, useSubmitExam } from '@/hooks/use-academy-exam'
import type { SubmitExamResponse } from '@/lib/api/academy-exam'
import { shuffleOptions } from '@/lib/quiz-shuffle'
import { cn } from '@/lib/utils'

function optionLabel(i: number): string {
  return String.fromCharCode(65 + i)
}

export function ExamRunner() {
  const stageSlug = useSearchParams().get('stage') ?? ''
  const stage = ACADEMY_STAGES.find((s) => s.slug === stageSlug)

  const { isLoggedIn, passedSet } = useExamResults()
  const alreadyGraduated = passedSet.has(stageSlug)
  const questionsQuery = useExamQuestions(stageSlug, isLoggedIn && !!stage)
  const submit = useSubmitExam()

  const [picked, setPicked] = useState<Record<number, number>>({})
  const [result, setResult] = useState<SubmitExamResponse | null>(null)
  const [seed, setSeed] = useState(0) // 重考时 +1 → 重新洗牌

  const questions = questionsQuery.data?.questions
  // ★ 每题洗牌(seed 变 → 重洗)· order 用于提交时映射回原序
  const shuffled = useMemo(
    () => (questions ?? []).map((q) => shuffleOptions(q.options)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [questions, seed],
  )

  const allAnswered =
    !!questions && questions.length > 0 && Object.keys(picked).length === questions.length

  function handleSubmit() {
    if (!questions || !allAnswered) return
    // 用户选的是展示下标 → order 映射回原序下标(后端按原序判分)
    const answers = shuffled.map((sq, qi) => sq.order[picked[qi]] ?? -1)
    submit.mutate(
      { stage: stageSlug, answers },
      { onSuccess: (res) => setResult(res) },
    )
  }

  function handleRetake() {
    setResult(null)
    setPicked({})
    setSeed((s) => s + 1)
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-3xl px-6 py-6">
          {/* 面包屑 */}
          <nav className="mb-6 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <Link href="/academy" className="transition-colors hover:text-midas-red">
              训练营
            </Link>
            {stage && (
              <>
                <ChevronRight className="h-3 w-3 text-muted-foreground/50" />
                <Link
                  href={`/academy/stage?s=${stage.slug}`}
                  className="transition-colors hover:text-midas-red"
                >
                  {stage.name}
                </Link>
              </>
            )}
            <ChevronRight className="h-3 w-3 text-muted-foreground/50" />
            <span className="text-foreground/70">结业测验</span>
          </nav>

          {!stage ? (
            <Placeholder text="模块不存在" />
          ) : !isLoggedIn ? (
            <LoginGate stageName={stage.name} />
          ) : (
            <>
              <header className="mb-6">
                <div className="flex items-center gap-2">
                  <h1 className="font-serif text-2xl font-bold">{stage.name} · 结业测验</h1>
                  {alreadyGraduated && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-gold/50 bg-gold/10 px-2.5 py-0.5 text-xs font-medium text-gold">
                      <Award className="h-3.5 w-3.5" />
                      已结业
                    </span>
                  )}
                </div>
                {questionsQuery.data && (
                  <p className="mt-2 text-sm text-muted-foreground">
                    共 {questionsQuery.data.total} 题 · 答对 ≥ {questionsQuery.data.pass_line} 题达标 ·
                    可重考
                  </p>
                )}
              </header>

              {questionsQuery.isLoading && <Placeholder text="加载题目中…" />}
              {questionsQuery.isError && <Placeholder text="题目加载失败,请刷新重试" />}

              {/* 结果态 */}
              {result && <ResultView result={result} onRetake={handleRetake} stageName={stage.name} />}

              {/* 答题态 */}
              {!result && questions && questions.length > 0 && (
                <>
                  <div className="space-y-5">
                    {questions.map((q, qi) => {
                      const sq = shuffled[qi]
                      const chosen = picked[qi]
                      return (
                        <div
                          key={qi}
                          className="rounded-xl border border-paper bg-cream p-4 shadow-sm sm:p-5"
                        >
                          <div className="flex gap-2.5">
                            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-midas-red/10 font-mono text-xs text-midas-red">
                              {qi + 1}
                            </span>
                            <p className="font-medium leading-relaxed text-foreground">{q.stem}</p>
                          </div>
                          <ul className="mt-3 space-y-2">
                            {sq.options.map((opt, oi) => {
                              const isChosen = chosen === oi
                              return (
                                <li key={oi}>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setPicked((prev) => ({ ...prev, [qi]: oi }))
                                    }
                                    aria-pressed={isChosen}
                                    className={cn(
                                      'flex w-full items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors',
                                      isChosen
                                        ? 'border-midas-red bg-midas-red-glow text-midas-red'
                                        : 'border-paper bg-background hover:border-midas-red/40',
                                    )}
                                  >
                                    <span className="flex h-5 w-5 shrink-0 items-center justify-center font-mono text-xs">
                                      {optionLabel(oi)}
                                    </span>
                                    <span className="flex-1">{opt}</span>
                                  </button>
                                </li>
                              )
                            })}
                          </ul>
                        </div>
                      )
                    })}
                  </div>

                  <div className="mt-6 flex items-center gap-3">
                    <button
                      type="button"
                      disabled={!allAnswered || submit.isPending}
                      onClick={handleSubmit}
                      className="rounded-lg bg-midas-red px-5 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                    >
                      {submit.isPending ? '判分中…' : '提交结业测验'}
                    </button>
                    {!allAnswered && (
                      <span className="text-xs text-muted-foreground">答完全部题目后可提交</span>
                    )}
                    {submit.isError && (
                      <span className="text-xs text-midas-red">提交失败,请重试</span>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function ResultView({
  result,
  onRetake,
  stageName,
}: {
  result: SubmitExamResponse
  onRetake: () => void
  stageName: string
}) {
  return (
    <div>
      {/* 得分横幅 */}
      <div
        className={cn(
          'rounded-xl border p-5 text-center shadow-sm',
          result.passed ? 'border-gold/50 bg-gold/10' : 'border-paper bg-cream',
        )}
      >
        {result.passed ? (
          <>
            <Award className="mx-auto h-10 w-10 text-gold" />
            <p className="mt-2 font-serif text-xl font-bold text-gold">
              🎉 恭喜结业 · {stageName}
            </p>
          </>
        ) : (
          <p className="font-serif text-xl font-bold text-foreground">未通过 · 可重考</p>
        )}
        <p className="mt-2 text-sm text-muted-foreground">
          得分 {result.score}/{result.total} · 达标线 {result.pass_line} 题
        </p>
        <button
          type="button"
          onClick={onRetake}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-midas-red/40 px-4 py-2 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow"
        >
          <RotateCcw className="h-4 w-4" />
          {result.passed ? '再考一次' : '重新测验'}
        </button>
      </div>

      {/* 逐题复盘(解析) */}
      <div className="mt-6 space-y-3">
        {result.results.map((r) => (
          <div
            key={r.question_index}
            className={cn(
              'rounded-lg border px-4 py-3 text-sm',
              r.is_correct ? 'border-success/30 bg-success/5' : 'border-midas-red/30 bg-midas-red/5',
            )}
          >
            <p
              className={cn(
                'flex items-center gap-1.5 font-medium',
                r.is_correct ? 'text-success' : 'text-midas-red',
              )}
            >
              {r.is_correct ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              第 {r.question_index + 1} 题 · {r.is_correct ? '答对' : '答错'}
            </p>
            <p className="mt-1 text-foreground/80">{r.explanation}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function LoginGate({ stageName }: { stageName: string }) {
  return (
    <div className="rounded-xl border border-dashed border-paper bg-surface-subtle p-8 text-center">
      <p className="text-sm text-muted-foreground">
        登录后参加「{stageName}」结业测验,成绩与结业状态将自动记录。
      </p>
      <Link
        href="/login"
        className="mt-4 inline-block rounded-md border border-midas-red/40 px-4 py-2 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow"
      >
        去登录
      </Link>
    </div>
  )
}

function Placeholder({ text }: { text: string }) {
  return (
    <div className="py-16 text-center">
      <p className="text-sm text-muted-foreground">{text}</p>
      <Link
        href="/academy"
        className="mt-3 inline-flex items-center gap-1 text-sm text-midas-red hover:underline"
      >
        <Home className="h-4 w-4" />
        返回训练营首页
      </Link>
    </div>
  )
}
