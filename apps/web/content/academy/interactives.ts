/**
 * 训练营文章 → D 系列交互组件 映射 · 纯数据(按 slug 索引,可逐篇/逐批增量)。
 * 与 quizzes.ts / practice.ts 同构:Record<slug, key[]> + getter(无 → null,不渲染)。
 * key 用语义名(非 D 编号);组件物理位置/D 编号变动不影响本表。
 * ⛔ 零 [id] 路由 · 纯前端 · 不碰后端/交易。
 *
 * 命名空间已为 5 批共 21 个组件预留(见《完整工作计划》);逐批实现时把对应 key 接入
 * 注册表(article-interactives.tsx)与下方 ACADEMY_INTERACTIVES 即可,机制不变。
 */
export type InteractiveKey =
  // —— 第一批:已实现 ——
  | 'liquidation'         // D1 爆仓价
  | 'chan-pivot'          // D2 缠论中枢
  | 'kline'               // D3 K线构成
  // —— 第二批:合约与风控 ——
  | 'funding-rate'        // D4 资金费率
  | 'position-sizing'     // D5 1%风险法/仓位反推
  | 'margin-mode'         // D6 保证金模式(全仓/逐仓)
  | 'pnl-exposure'        // D7 盈亏与敞口
  | 'liquidation-process' // D8 爆仓全过程
  // —— 第三批:技术指标 ——
  | 'moving-average'      // D9 均线/金叉死叉
  | 'macd'                // D10 MACD 金叉
  | 'bollinger'           // D11 布林带
  | 'rsi'                 // D12 RSI
  | 'kdj'                 // D13 KDJ
  // —— 第四批:缠论结构 ——
  | 'kline-merge'         // D14 K线包含处理
  | 'fractal-bi'          // D15 分型与笔
  | 'divergence'          // D16 背驰
  | 'buy-sell-points'     // D17 三类买卖点(结构术语,非买卖指令)
  // —— 第五批:策略与交易体系 ——
  | 'risk-reward'         // D18 风险回报比
  | 'trend-range'         // D19 趋势 vs 震荡
  | 'grid-trading'        // D20 网格
  | 'martingale'          // D21 马丁格尔(反面演示)

/** 已实现 key(注册表中已挂组件)· 数据完整性自检用 · 逐批扩展时同步追加 */
export const IMPLEMENTED_KEYS = [
  // 第一批
  'liquidation', 'chan-pivot', 'kline',
  // 第二批:合约与风控
  'funding-rate', 'position-sizing', 'margin-mode', 'pnl-exposure', 'liquidation-process',
  // 第三批:技术指标(D9-D13;D13 kdj 锚 B10)
  'moving-average', 'macd', 'bollinger', 'rsi', 'kdj',
  // 第四批:缠论结构
  'kline-merge', 'fractal-bi', 'divergence', 'buy-sell-points',
  // 第五批:策略与交易体系
  'risk-reward', 'trend-range', 'grid-trading', 'martingale',
] as const

/** 运行期已知 key 全集(防 as 强转引入的拼写错误;与联合类型同步) */
export const ALL_KEYS: readonly InteractiveKey[] = [
  'liquidation', 'chan-pivot', 'kline',
  'funding-rate', 'position-sizing', 'margin-mode', 'pnl-exposure', 'liquidation-process',
  'moving-average', 'macd', 'bollinger', 'rsi', 'kdj',
  'kline-merge', 'fractal-bi', 'divergence', 'buy-sell-points',
  'risk-reward', 'trend-range', 'grid-trading', 'martingale',
]

/** 文章 slug → 要嵌入的交互组件(按数组顺序渲染)· 首批锚文跑通机制后逐篇增量 */
export const ACADEMY_INTERACTIVES: Record<string, InteractiveKey[]> = {
  // 第一批锚文
  E4: ['liquidation'],
  C7: ['chan-pivot'],
  A2: ['kline'],
  // 第二批锚文(合约风控;锚文存在性由落地时核对 manifest,不存在则换同组件的其它配套文)
  E2: ['funding-rate'],
  F4: ['position-sizing'],
  E3: ['margin-mode'],
  E8: ['pnl-exposure'],
  'C2-4': ['liquidation-process'],
  // 第三批锚文(技术指标 · B 系列;manifest 已核 B2/B5/B7/B9 存在)
  B2: ['moving-average'],
  B5: ['macd'],
  B7: ['bollinger'],
  B9: ['rsi'],
  B10: ['kdj'],
  // —— 第四批:缠论结构(锚 C 系列缠论文)——
  C3: ['kline-merge'],
  C5: ['fractal-bi'],
  'C1-7': ['divergence'],
  C8: ['buy-sell-points'],
  // —— 第五批:策略与交易体系(锚最贴主题文;D18 risk-reward/D19 trend-range 在 strategy 阶无精准文,跨 system 阶 F3/F8 替换,见回报)——
  F3: ['risk-reward'],
  F8: ['trend-range'],
  'C3-8': ['grid-trading'],
  'C3-9': ['martingale'],
}

/** 取某篇要嵌入的交互组件 key 列表(无 → null,不渲染交互区) */
export function getInteractives(slug: string): InteractiveKey[] | null {
  return ACADEMY_INTERACTIVES[slug] ?? null
}
