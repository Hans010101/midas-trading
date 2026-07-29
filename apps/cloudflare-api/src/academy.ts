import examBankJson from '../../api/app/services/academy/exam_questions.json'
import examBankEnJson from '../../api/app/services/academy/exam_questions.en.json'
import {
  ACADEMY_ARTICLES,
  ACADEMY_STAGES,
} from '../../web/content/academy/manifest'

import { authenticate, type AuthenticatedUser } from './auth'
import { COMMERCIAL_MEMBERSHIP_ENABLED } from './features'
import {
  HttpError,
  bearerToken,
  jsonResponse,
  readJsonObject,
  requireString,
} from './http'

const PASS_RATIO = 0.8
const AWARD_DAYS = 7
const DAY_MS = 24 * 60 * 60 * 1_000

type ExamQuestion = Readonly<{
  question: string
  options: string[]
  answerIndex: number
  explanation: string
}>

type ExamBank = Readonly<Record<string, ExamQuestion[]>>

const EXAM_BANK = examBankJson as ExamBank
const EXAM_BANK_EN = examBankEnJson as ExamBank
const ARTICLE_STAGE = new Map(
  ACADEMY_ARTICLES.map((article) => [article.slug, article.stage]),
)
const STAGE_TOTALS = Object.fromEntries(
  ACADEMY_STAGES.map((stage) => [
    stage.slug,
    ACADEMY_ARTICLES.filter((article) => article.stage === stage.slug).length,
  ]),
)
const TOTAL_ARTICLES = ACADEMY_ARTICLES.length

async function optionalAuthenticate(
  request: Request,
  env: Env,
): Promise<AuthenticatedUser | null> {
  return bearerToken(request) ? authenticate(request, env) : null
}

function validArticleSlug(value: unknown): {
  slug: string
  stage: string
} {
  if (typeof value !== 'string' || value.length < 1 || value.length > 32) {
    throw new HttpError(422, 'article_slug 格式无效')
  }
  const slug = value.trim()
  const stage = ARTICLE_STAGE.get(slug)
  if (!stage) throw new HttpError(400, `未知训练营文章：${slug}`)
  return { slug, stage }
}

function validStage(value: string, locale: 'zh' | 'en' = 'zh'): {
  stage: string
  questions: ExamQuestion[]
} {
  const stage = value.trim()
  const questions = (locale === 'en' ? EXAM_BANK_EN : EXAM_BANK)[stage]
  if (!questions) throw new HttpError(400, `未知结业测验模块：${stage}`)
  return { stage, questions }
}

function emptyProgress() {
  return {
    completed_slugs: [] as string[],
    by_stage: {} as Record<string, number>,
    stage_totals: STAGE_TOTALS,
    total_completed: 0,
    total_articles: TOTAL_ARTICLES,
  }
}

async function getProgress(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const auth = await optionalAuthenticate(request, env)
  if (!auth) {
    return jsonResponse(emptyProgress(), 200, requestId, request.method)
  }
  const rows = await env.DB
    .prepare(
      `SELECT article_slug, stage
       FROM academy_progress
       WHERE user_id = ?
       ORDER BY completed_at ASC`,
    )
    .bind(auth.user.id)
    .all<{ article_slug: string; stage: string }>()
  const byStage: Record<string, number> = {}
  const completedSlugs = rows.results.map((row) => {
    byStage[row.stage] = (byStage[row.stage] ?? 0) + 1
    return row.article_slug
  })
  return jsonResponse(
    {
      completed_slugs: completedSlugs,
      by_stage: byStage,
      stage_totals: STAGE_TOTALS,
      total_completed: completedSlugs.length,
      total_articles: TOTAL_ARTICLES,
    },
    200,
    requestId,
    request.method,
  )
}

async function completeArticle(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const { slug, stage } = validArticleSlug(body.article_slug)
  const completedAt = Date.now()
  const inserted = await env.DB
    .prepare(
      `INSERT OR IGNORE INTO academy_progress
        (user_id, article_slug, stage, completed_at)
       VALUES (?, ?, ?, ?)`,
    )
    .bind(user.id, slug, stage, completedAt)
    .run()
  const row = await env.DB
    .prepare(
      `SELECT completed_at
       FROM academy_progress
       WHERE user_id = ? AND article_slug = ?`,
    )
    .bind(user.id, slug)
    .first<{ completed_at: number }>()
  if (!row) throw new Error('academy progress insert did not persist')
  return jsonResponse(
    {
      article_slug: slug,
      stage,
      completed_at: new Date(row.completed_at).toISOString(),
      newly_completed: inserted.meta.changes === 1,
    },
    200,
    requestId,
    request.method,
  )
}

async function uncompleteArticle(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const { slug } = validArticleSlug(
    new URL(request.url).searchParams.get('article_slug'),
  )
  const deleted = await env.DB
    .prepare(
      `DELETE FROM academy_progress
       WHERE user_id = ? AND article_slug = ?`,
    )
    .bind(user.id, slug)
    .run()
  return jsonResponse(
    { article_slug: slug, removed: deleted.meta.changes === 1 },
    200,
    requestId,
    request.method,
  )
}

function examQuestions(
  request: Request,
  requestId: string,
): Response {
  const stageParam = new URL(request.url).searchParams.get('stage')
  const locale = new URL(request.url).searchParams.get('locale') === 'en' ? 'en' : 'zh'
  if (!stageParam || stageParam.length > 16) {
    throw new HttpError(422, 'stage 格式无效')
  }
  const { stage, questions } = validStage(stageParam, locale)
  const total = questions.length
  return jsonResponse(
    {
      stage,
      questions: questions.map(({ question, options }) => ({
        stem: question,
        options,
      })),
      total,
      pass_line: Math.ceil(total * PASS_RATIO),
      pass_ratio: PASS_RATIO,
    },
    200,
    requestId,
    request.method,
  )
}

function parseAnswers(value: unknown): number[] {
  if (!Array.isArray(value) || value.length > 100) {
    throw new HttpError(422, 'answers 格式无效')
  }
  if (
    value.some(
      (answer) => typeof answer !== 'number' || !Number.isSafeInteger(answer),
    )
  ) {
    throw new HttpError(422, 'answers 必须是整数数组')
  }
  return value as number[]
}

async function submitExam(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const locale = body.locale === 'en' ? 'en' : 'zh'
  const { stage, questions } = validStage(
    requireString(body, 'stage', { min: 1, max: 16 }),
    locale,
  )
  const answers = parseAnswers(body.answers)
  let score = 0
  const results = questions.map((question, questionIndex) => {
    const yourAnswer = answers[questionIndex] ?? null
    const isCorrect = yourAnswer === question.answerIndex
    if (isCorrect) score += 1
    return {
      question_index: questionIndex,
      your_answer: yourAnswer,
      correct_answer: question.answerIndex,
      is_correct: isCorrect,
      explanation: question.explanation,
    }
  })
  const total = questions.length
  const passLine = Math.ceil(total * PASS_RATIO)
  const passed = total > 0 && score >= passLine
  const timestamp = Date.now()
  let membershipAwarded = false
  let newExpiresAt: string | null = null

  if (passed && COMMERCIAL_MEMBERSHIP_ENABLED) {
    const awardId = crypto.randomUUID()
    const statements = await env.DB.batch([
      env.DB
        .prepare(
          `INSERT INTO academy_exam_results
            (id, user_id, stage, score, total, passed, created_at)
           VALUES (?, ?, ?, ?, ?, 1, ?)`,
        )
        .bind(
          crypto.randomUUID(),
          user.id,
          stage,
          score,
          total,
          timestamp,
        ),
      env.DB
        .prepare(
          `INSERT OR IGNORE INTO academy_exam_awards
            (id, user_id, stage, awarded_days, awarded_at)
           VALUES (?, ?, ?, ?, ?)`,
        )
        .bind(awardId, user.id, stage, AWARD_DAYS, timestamp),
      env.DB
        .prepare(
          `UPDATE users
           SET subscription_expires_at =
                 CASE
                   WHEN subscription_expires_at IS NULL
                     OR subscription_expires_at < ?
                   THEN ?
                   ELSE subscription_expires_at + ?
                 END,
               updated_at = ?
           WHERE id = ?
             AND EXISTS (
               SELECT 1 FROM academy_exam_awards WHERE id = ?
             )`,
        )
        .bind(
          timestamp,
          timestamp + AWARD_DAYS * DAY_MS,
          AWARD_DAYS * DAY_MS,
          timestamp,
          user.id,
          awardId,
        ),
    ])
    membershipAwarded = statements[1]?.meta.changes === 1
    if (membershipAwarded) {
      const expiry = await env.DB
        .prepare('SELECT subscription_expires_at FROM users WHERE id = ?')
        .bind(user.id)
        .first<{ subscription_expires_at: number }>()
      newExpiresAt = expiry
        ? new Date(expiry.subscription_expires_at).toISOString()
        : null
    }
  } else {
    await env.DB
      .prepare(
        `INSERT INTO academy_exam_results
          (id, user_id, stage, score, total, passed, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        crypto.randomUUID(),
        user.id,
        stage,
        score,
        total,
        passed ? 1 : 0,
        timestamp,
      )
      .run()
  }

  return jsonResponse(
    {
      stage,
      score,
      total,
      pass_line: passLine,
      passed,
      results,
      membership_awarded: membershipAwarded,
      new_expires_at: newExpiresAt,
    },
    200,
    requestId,
    request.method,
  )
}

async function examResults(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const auth = await optionalAuthenticate(request, env)
  if (!auth) {
    return jsonResponse({ results: [] }, 200, requestId, request.method)
  }
  const rows = await env.DB
    .prepare(
      `SELECT
         stage,
         MAX(passed) AS passed,
         MAX(score) AS best_score,
         MAX(total) AS total,
         COUNT(*) AS attempts
       FROM academy_exam_results
       WHERE user_id = ?
       GROUP BY stage
       ORDER BY MIN(created_at) ASC`,
    )
    .bind(auth.user.id)
    .all<{
      stage: string
      passed: number
      best_score: number
      total: number
      attempts: number
    }>()
  return jsonResponse(
    {
      results: rows.results.map((row) => ({
        stage: row.stage,
        passed: row.passed === 1,
        best_score: row.best_score,
        total: row.total,
        attempts: row.attempts,
      })),
    },
    200,
    requestId,
    request.method,
  )
}

export async function handleAcademyRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const route = `${request.method} ${path}`
  switch (route) {
    case 'GET /api/v1/academy/progress':
      return getProgress(request, env, requestId)
    case 'POST /api/v1/academy/progress/complete':
      return completeArticle(request, env, requestId)
    case 'DELETE /api/v1/academy/progress/complete':
      return uncompleteArticle(request, env, requestId)
    case 'GET /api/v1/academy/exam':
      return examQuestions(request, requestId)
    case 'POST /api/v1/academy/exam/submit':
      return submitExam(request, env, requestId)
    case 'GET /api/v1/academy/exam/results':
      return examResults(request, env, requestId)
    default:
      return path.startsWith('/api/v1/academy/')
        ? jsonResponse(
            { detail: 'Route not found' },
            404,
            requestId,
            request.method,
          )
        : null
  }
}
