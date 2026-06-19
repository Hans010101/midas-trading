/**
 * 学习进度分母计算 + 自动标记判定 · 训练营 B 期刀1.5(纯逻辑 · 可单测)。
 *
 * ★分母只算「有小测的文章」:刀1.5 改为「答完小测 = 学完」,无小测的文章(如 F36)
 *   无法触发标记 → 不计入进度分母,避免永远学不完的孤儿文章。
 * 「有小测」= slug 在 ACADEMY_QUIZZES 表中(题库数据零改 · 此处只读 keys)。
 * 进度端点(刀1)零改 —— 分母在前端按 quiz-slug 集过滤。
 */

import { ACADEMY_ARTICLES } from '@/content/academy/manifest'
import { ACADEMY_QUIZZES } from '@/content/academy/quizzes'

/** 有小测的文章 slug 集(进度分子/分母都只认这些)。 */
export const QUIZ_SLUGS: ReadonlySet<string> = new Set(Object.keys(ACADEMY_QUIZZES))

const SLUG_STAGE: ReadonlyMap<string, string> = new Map(
  ACADEMY_ARTICLES.map((a) => [a.slug, a.stage]),
)

/** 某阶有小测的文章数(进度分母 Y · 不含 F36/无小测篇)。 */
export function stageQuizTotal(stageSlug: string): number {
  return ACADEMY_ARTICLES.filter((a) => a.stage === stageSlug && QUIZ_SLUGS.has(a.slug)).length
}

/**
 * 某阶已完成的「有小测」文章数(进度分子 X)。
 * 从后端 completed_slugs 过滤:① 有小测 ② 属该阶 —— 排除任何非小测残留标记。
 */
export function stageQuizDone(completedSlugs: readonly string[], stageSlug: string): number {
  return completedSlugs.filter((s) => QUIZ_SLUGS.has(s) && SLUG_STAGE.get(s) === stageSlug).length
}

/**
 * 是否应触发「答完自动标记学完」· 纯判定(组件 useEffect 调它)。
 * 条件全满足才触发:本篇所有题已答 + 已登录 + 尚未标记完成 + 无进行中请求(防重复)。
 */
export function shouldAutoMark(p: {
  allAnswered: boolean
  isLoggedIn: boolean
  alreadyCompleted: boolean
  isPending: boolean
}): boolean {
  return p.allAnswered && p.isLoggedIn && !p.alreadyCompleted && !p.isPending
}
