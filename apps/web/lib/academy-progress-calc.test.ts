import { describe, expect, it } from 'vitest'

import { ACADEMY_QUIZZES } from '@/content/academy/quizzes'

import {
  QUIZ_SLUGS,
  shouldAutoMark,
  stageQuizDone,
  stageQuizTotal,
} from './academy-progress-calc'

describe('QUIZ_SLUGS · 有小测文章集', () => {
  it('= ACADEMY_QUIZZES 的全部 key', () => {
    expect(QUIZ_SLUGS.size).toBe(Object.keys(ACADEMY_QUIZZES).length)
    expect(QUIZ_SLUGS.has('A2')).toBe(true) // A2 有小测(quizzes.test 已钉)
  })
})

describe('stageQuizTotal · 分母只算有小测的文章', () => {
  it('basics 分母 > 0 且不超过该阶文章总数', () => {
    expect(stageQuizTotal('basics')).toBeGreaterThan(0)
  })
  it('未知阶 → 0', () => {
    expect(stageQuizTotal('不存在的阶')).toBe(0)
  })
})

describe('stageQuizDone · 分子过滤(有小测 ∩ 该阶)', () => {
  it('A2/A3 属 basics 且有小测 → 计 2', () => {
    expect(stageQuizDone(['A2', 'A3'], 'basics')).toBe(2)
  })
  it('★非小测 / 不存在的 slug 不计(防脏标记膨胀分子)', () => {
    expect(stageQuizDone(['__not_a_quiz_slug__'], 'basics')).toBe(0)
  })
  it('跨阶不串:A2(basics)不计入 technical', () => {
    expect(stageQuizDone(['A2'], 'technical')).toBe(0)
  })
  it('空进度 → 0', () => {
    expect(stageQuizDone([], 'basics')).toBe(0)
  })
})

describe('shouldAutoMark · 答完自动标记判定', () => {
  const base = {
    allAnswered: true,
    isLoggedIn: true,
    alreadyCompleted: false,
    isPending: false,
  }
  it('全满足 → 触发', () => {
    expect(shouldAutoMark(base)).toBe(true)
  })
  it('★没答完 → 不触发', () => {
    expect(shouldAutoMark({ ...base, allAnswered: false })).toBe(false)
  })
  it('★未登录 → 不触发', () => {
    expect(shouldAutoMark({ ...base, isLoggedIn: false })).toBe(false)
  })
  it('★已完成 → 不触发(幂等防重复)', () => {
    expect(shouldAutoMark({ ...base, alreadyCompleted: true })).toBe(false)
  })
  it('请求进行中 → 不触发(防重复)', () => {
    expect(shouldAutoMark({ ...base, isPending: true })).toBe(false)
  })
})
