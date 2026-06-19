/** 训练营题库数据完整性 · 防增量补题时写错 answerIndex / 留空字段(纯数据钉死)。 */

import { describe, expect, it } from 'vitest'

import { ACADEMY_QUIZZES, getQuiz } from './quizzes'

describe('ACADEMY_QUIZZES 数据完整性', () => {
  it('样例题就位(A2 / A3 各 ≥2 题)', () => {
    expect(getQuiz('A2').length).toBeGreaterThanOrEqual(2)
    expect(getQuiz('A3').length).toBeGreaterThanOrEqual(2)
  })

  it('无题文章 getQuiz 返回空数组', () => {
    expect(getQuiz('不存在的slug')).toEqual([])
  })

  it.each(Object.entries(ACADEMY_QUIZZES))('「%s」每题结构合法', (_slug, questions) => {
    for (const q of questions) {
      expect(q.stem.trim().length).toBeGreaterThan(0)
      expect(q.explanation.trim().length).toBeGreaterThan(0)
      expect(q.options.length).toBeGreaterThanOrEqual(2)
      expect(q.options.every((o) => o.trim().length > 0)).toBe(true)
      // answerIndex 必须是整数且落在 options 范围内(否则前端永远判不出正确项)
      expect(Number.isInteger(q.answerIndex)).toBe(true)
      expect(q.answerIndex).toBeGreaterThanOrEqual(0)
      expect(q.answerIndex).toBeLessThan(q.options.length)
    }
  })
})
