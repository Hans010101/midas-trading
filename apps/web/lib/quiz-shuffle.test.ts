import { describe, expect, it } from 'vitest'

import { shuffleQuestion } from './quiz-shuffle'

const Q = { options: ['正确项', 'B', 'C', 'D'], answerIndex: 0 }

describe('shuffleQuestion · 选项洗牌', () => {
  it('选项集合不变(只换顺序,不增删改内容)', () => {
    const s = shuffleQuestion(Q, () => 0.5)
    expect([...s.options].sort()).toEqual([...Q.options].sort())
    expect(s.options).toHaveLength(4)
  })

  it('★正确答案下标追踪到洗牌后位置(值仍是原正确项)· 100 次不变式', () => {
    for (let n = 0; n < 100; n++) {
      const s = shuffleQuestion(Q) // Math.random
      expect(s.options[s.answerIndex]).toBe(Q.options[Q.answerIndex])
    }
  })

  it('★打散有效:多次洗牌正确答案落在 >1 个位置(不再固定 B/原位)', () => {
    const positions = new Set<number>()
    for (let n = 0; n < 300; n++) positions.add(shuffleQuestion(Q).answerIndex)
    expect(positions.size).toBeGreaterThan(1)
  })

  it('确定性 rng → 可复现 + 答案值正确', () => {
    const rng = () => 0 // 每次 j=0
    const s = shuffleQuestion({ options: ['a', 'b', 'c', 'd'], answerIndex: 1 }, rng)
    expect(s.options[s.answerIndex]).toBe('b')
    expect([...s.options].sort()).toEqual(['a', 'b', 'c', 'd'])
  })

  it('两选项也安全(集合一致 + 答案追踪)', () => {
    const s = shuffleQuestion({ options: ['对', '错'], answerIndex: 1 })
    expect(s.options[s.answerIndex]).toBe('错')
    expect(s.options).toHaveLength(2)
  })
})
