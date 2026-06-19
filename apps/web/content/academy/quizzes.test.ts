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

// E组+C组+F组第一期(35 篇 84 题)· 显式覆盖新增 slug
const ECF_SLUGS = [
  'E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7', 'E8', 'E9', 'E10',
  'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9',
  'F2', 'F3', 'F4', 'F6', 'F8', 'F9', 'F12', 'F13', 'F14', 'F15', 'F16', 'F17', 'F21', 'F22', 'F23', 'F24',
] as const

describe('E/C/F 组随堂小测(35 篇 84 题)', () => {
  it('35 篇 slug 全部就位、各有题', () => {
    expect(ECF_SLUGS.length).toBe(35)
    for (const slug of ECF_SLUGS) {
      expect(getQuiz(slug).length).toBeGreaterThan(0)
    }
  })

  it('全批合计 84 题', () => {
    const total = ECF_SLUGS.reduce((n, s) => n + getQuiz(s).length, 0)
    expect(total).toBe(84)
  })

  it.each(ECF_SLUGS)('「%s」每题:选项固定 4 个 + answerIndex 0–3 + 题干/解析非空', (slug) => {
    const questions = getQuiz(slug)
    expect(questions.length).toBeGreaterThan(0)
    for (const q of questions) {
      expect(q.options.length).toBe(4)
      expect(Number.isInteger(q.answerIndex)).toBe(true)
      expect(q.answerIndex).toBeGreaterThanOrEqual(0)
      expect(q.answerIndex).toBeLessThanOrEqual(3)
      expect(q.stem.trim().length).toBeGreaterThan(0)
      expect(q.explanation.trim().length).toBeGreaterThan(0)
      expect(q.options.every((o) => o.trim().length > 0)).toBe(true)
    }
  })
})

// 第二期(54 篇 70 题)· C1-1~20 缠论进阶 + C2 案例库 + C3 策略 + F 理念篇
const BATCH2_SLUGS = [
  'C1-1', 'C1-2', 'C1-3', 'C1-4', 'C1-5', 'C1-6', 'C1-7', 'C1-8', 'C1-9', 'C1-10',
  'C1-11', 'C1-12', 'C1-13', 'C1-14', 'C1-15', 'C1-16', 'C1-17', 'C1-18', 'C1-19', 'C1-20',
  'C2-1', 'C2-2', 'C2-3', 'C2-4', 'C2-5', 'C2-6', 'C2-7', 'C2-8', 'C2-9', 'C2-10',
  'C3-1', 'C3-2', 'C3-3', 'C3-4', 'C3-5', 'C3-6', 'C3-7', 'C3-8', 'C3-9', 'C3-10',
  'F1', 'F5', 'F7', 'F10', 'F11', 'F18', 'F19', 'F20', 'F25', 'F26', 'F27', 'F28', 'F37', 'F38',
] as const

describe('第二期 C1进阶/C2/C3/F理念(54 篇 70 题)', () => {
  it('54 篇 slug 全部就位、各有题', () => {
    expect(BATCH2_SLUGS.length).toBe(54)
    for (const slug of BATCH2_SLUGS) {
      expect(getQuiz(slug).length).toBeGreaterThan(0)
    }
  })

  it('全批合计 70 题', () => {
    const total = BATCH2_SLUGS.reduce((n, s) => n + getQuiz(s).length, 0)
    expect(total).toBe(70)
  })

  it.each(BATCH2_SLUGS)('「%s」每题:选项固定 4 个 + answerIndex 0–3 + 题干/解析非空', (slug) => {
    const questions = getQuiz(slug)
    expect(questions.length).toBeGreaterThan(0)
    for (const q of questions) {
      expect(q.options.length).toBe(4)
      expect(Number.isInteger(q.answerIndex)).toBe(true)
      expect(q.answerIndex).toBeGreaterThanOrEqual(0)
      expect(q.answerIndex).toBeLessThanOrEqual(3)
      expect(q.stem.trim().length).toBeGreaterThan(0)
      expect(q.explanation.trim().length).toBeGreaterThan(0)
      expect(q.options.every((o) => o.trim().length > 0)).toBe(true)
    }
  })
})
