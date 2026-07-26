/**
 * 模块结业测验 API client · 训练营 B 期刀2。
 *
 * GET    /api/v1/academy/exam?stage=       → 某模块结业测验题(★只 stem+options,无答案)
 * POST   /api/v1/academy/exam/submit       → 提交选项(原序下标)· ★后端判分 · 记成绩
 * GET    /api/v1/academy/exam/results      → 各模块结业状态(未登录返空)
 *
 * 🔴 防作弊:正确答案只在后端 · 前端拿题不拿答案 · 提交选项后端重新判分 · 成绩存后端(非 localStorage)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export interface ExamQuestionPublic {
  stem: string
  options: string[] // ★ 无 answerIndex
}

export interface ExamQuestionsResponse {
  stage: string
  questions: ExamQuestionPublic[]
  total: number
  pass_line: number // 及格题数
  pass_ratio: number
}

export interface QuestionResult {
  question_index: number
  your_answer: number | null
  correct_answer: number // 提交后才有(供复盘)
  is_correct: boolean
  explanation: string
}

export interface SubmitExamResponse {
  stage: string
  score: number
  total: number
  pass_line: number
  passed: boolean
  results: QuestionResult[]
  // 刀3:首次达标发 1 周会员 · membership_awarded 仅首次达标 true(重考不重复发)
  membership_awarded: boolean
  new_expires_at: string | null // 本次发了会员才有(新会员到期日 ISO)
}

export interface ExamStatusItem {
  stage: string
  passed: boolean // 曾达标
  best_score: number
  total: number
  attempts: number
}

export interface ExamResultsResponse {
  results: ExamStatusItem[]
}

export async function fetchExamQuestions(
  stage: string,
  signal?: AbortSignal,
): Promise<ExamQuestionsResponse> {
  const r = await fetch(
    `${API_BASE}/api/v1/academy/exam?stage=${encodeURIComponent(stage)}`,
    { signal },
  )
  if (!r.ok) throw new Error(`exam questions HTTP ${r.status}`)
  return (await r.json()) as ExamQuestionsResponse
}

/** 提交结业测验 · answers = 每题选中的【原序】选项下标(前端洗牌后映射回原序)· 需登录。 */
export async function submitExam(
  stage: string,
  answers: number[],
  token: string,
): Promise<SubmitExamResponse> {
  const r = await fetch(`${API_BASE}/api/v1/academy/exam/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ stage, answers }),
  })
  if (!r.ok) throw new Error(`exam submit HTTP ${r.status}`)
  return (await r.json()) as SubmitExamResponse
}

export async function fetchExamResults(
  token?: string,
  signal?: AbortSignal,
): Promise<ExamResultsResponse> {
  const r = await fetch(`${API_BASE}/api/v1/academy/exam/results`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    signal,
  })
  if (!r.ok) throw new Error(`exam results HTTP ${r.status}`)
  return (await r.json()) as ExamResultsResponse
}
