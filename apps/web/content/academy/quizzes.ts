/**
 * 训练营随堂小测题库 · 纯数据(按文章 slug 索引,可逐篇增量)。
 *
 * 结构:Record<articleSlug, QuizQuestion[]>;无题的文章不在表中(→ 不渲染小测区)。
 * 前端判定:components/academy/article-quiz.tsx 点选项后比对 answerIndex,无后端。
 * 题目内容由产品方后续增量补充;此处先放 A2 / A3 样例题验证机制跑通。
 *
 * 沿用项目「manifest.ts 纯数据 + 组件读它渲染」范式(content/academy/manifest.ts)。
 */

export interface QuizQuestion {
  /** 题干 */
  stem: string
  /** 选项(≥2 个) */
  options: string[]
  /** 正确选项下标(0-based · 必须落在 options 范围内) */
  answerIndex: number
  /** 解析(答题后展示) */
  explanation: string
}

export const ACADEMY_QUIZZES: Record<string, QuizQuestion[]> = {
  A2: [
    {
      stem: '一根 K 线的「实体」是由哪两个价格围成的?',
      options: ['最高价和最低价', '开盘价和收盘价', '开盘价和最高价', '收盘价和最低价'],
      answerIndex: 1,
      explanation:
        '实体由开盘价和收盘价围成,两者之间的距离就是实体高度;连到最高价 / 最低价的细线是影线,不是实体。',
    },
    {
      stem: '在点金里(遵循 A 股「红涨绿跌」习惯),阳线(收盘价高于开盘价)用什么颜色?',
      options: ['绿色', '红色', '蓝色', '黑色'],
      answerIndex: 1,
      explanation:
        '点金遵循 A 股习惯,阳线(上涨)用红色、阴线(下跌)用绿色;注意美股和多数加密平台正好相反(绿涨红跌),看图前先确认平台颜色规则。',
    },
  ],
  A3: [
    {
      stem: '一根 K 线的「上影线」通常反映什么?',
      options: [
        '下方有买盘支撑',
        '上方存在卖压(价格冲高后被打回)',
        '这段时间一定会上涨',
        '没有任何含义',
      ],
      answerIndex: 1,
      explanation:
        '上影线是价格一度冲高、被卖压打回后留下的「尾巴」,反映上方存在卖压;它是多空博弈的信号,并不预示必涨必跌。',
    },
    {
      stem: '关于「长下影线(如锤子线)」,下列说法正确的是?',
      options: [
        '出现锤子线就一定会反转上涨',
        '它是潜在企稳信号,但需后续 K 线和其他信息验证,不能单凭一根就下结论',
        '下影线越长说明接下来跌得越狠',
        '影线纯属噪音,没有参考价值',
      ],
      answerIndex: 1,
      explanation:
        '长下影线反映下方有买盘承接,出现在低位常被视为潜在企稳信号;但它是「信号」不是「承诺」,专业做法是等待后续 K 线和其他信息验证。把单根影线当成涨跌铁律,是新手最容易犯的错。',
    },
  ],
}

/** 取某篇文章的小测题(无 → 空数组 → 不渲染小测区) */
export function getQuiz(slug: string): QuizQuestion[] {
  return ACADEMY_QUIZZES[slug] ?? []
}
