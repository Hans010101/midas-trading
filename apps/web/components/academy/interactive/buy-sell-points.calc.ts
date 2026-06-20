/**
 * D17 买卖点(缠论)· 纯计算逻辑。
 * ★★ 买卖点是缠论对【结构位置】的描述,是结构术语,【不是买卖指令/操作建议】。
 * ★★ 任何买卖点都【可能失败】;它【不预测】未来、出现买卖点【不保证】盈利。
 * 本函数仅做结构分类,不含任何交易语义。
 * 结构定义(以买点为例,卖点对称):
 *   二买 = 一买后回调不破前低(low > prevLow);
 *   三买 = 突破中枢后回踩不破中枢上沿 ZG(low > zgUpper)。
 */
export type PointType = 'buy2' | 'buy3' | 'sell2' | 'sell3' | 'none'

/** 二买:回调低点不破前低 → buy2,否则 none */
export function classifyBuy2(low: number, prevLow: number): PointType {
  return low > prevLow ? 'buy2' : 'none'
}

/** 三买:回踩低点不破中枢上沿 ZG → buy3,否则 none */
export function classifyBuy3(low: number, zgUpper: number): PointType {
  return low > zgUpper ? 'buy3' : 'none'
}

/** 二卖:反弹高点不破前高 → sell2(与二买对称) */
export function classifySell2(high: number, prevHigh: number): PointType {
  return high < prevHigh ? 'sell2' : 'none'
}

/** 三卖:反抽高点不破中枢下沿 ZD → sell3(与三买对称) */
export function classifySell3(high: number, zdLower: number): PointType {
  return high < zdLower ? 'sell3' : 'none'
}
