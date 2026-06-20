/**
 * 随堂小测选项洗牌 · 训练营 B 期刀1.5(纯逻辑 · 可单测)。
 *
 * 修正题库正确答案 79% 扎堆 B 位的问题:渲染时 Fisher-Yates 打散选项,
 * 正确答案随机落 A/B/C/D。★组件首次挂载洗一次(useState 惰性初始化),不每次 render 重洗。
 * 题库数据(quizzes.ts)零改动 —— 纯前端渲染时洗。新增题(含结业测验)自动享受打散。
 */

export interface ShuffledQuestion {
  /** 洗牌后的选项顺序 */
  options: string[]
  /** 正确答案在【洗牌后】的下标(判定用这个,不再用原始 answerIndex) */
  answerIndex: number
}

/**
 * 对单题选项做 Fisher-Yates 洗牌,返回洗牌后的 options + 正确答案的新下标。
 * rng 默认 Math.random;传入可注入确定性序列(测试用)。
 * 不改变选项内容(集合一致),只改顺序;正确答案追踪到新位置。
 */
export function shuffleQuestion(
  question: { options: string[]; answerIndex: number },
  rng: () => number = Math.random,
): ShuffledQuestion {
  const order = _shuffledOrder(question.options.length, rng)
  return {
    options: order.map((i) => question.options[i]),
    answerIndex: order.indexOf(question.answerIndex),
  }
}

export interface ShuffledOptions {
  /** 洗牌后的选项顺序(展示用) */
  options: string[]
  /** order[展示下标] = 原始下标 —— ★结业测验提交时把用户选中的展示下标映射回原序(后端按原序判分) */
  order: number[]
}

/**
 * 洗牌选项 · 用于结业测验(前端不知道正确答案,只需把选中位置映射回原序提交)。
 * 与 shuffleQuestion 区别:不追踪答案(答案在后端),而是吐 order 映射。
 */
export function shuffleOptions(
  options: string[],
  rng: () => number = Math.random,
): ShuffledOptions {
  const order = _shuffledOrder(options.length, rng)
  return { options: order.map((i) => options[i]), order }
}

/** Fisher-Yates 生成 [0..n) 的随机排列。 */
function _shuffledOrder(n: number, rng: () => number): number[] {
  const order = Array.from({ length: n }, (_, i) => i)
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1))
    const tmp = order[i]
    order[i] = order[j]
    order[j] = tmp
  }
  return order
}
