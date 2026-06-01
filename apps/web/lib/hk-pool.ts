/**
 * 港股策展池(前端常量)· 港股阶段二 单元3。
 *
 * ★ 与后端 apps/api/app/services/hk_pool.py 的 HK_POOL 对齐(18 只 · 科技/金融/电信/汽车)。
 * 为什么前端硬编码:`symbols?market=hk` 受 q(min_length=1)约束,无法一次取全 18 只;
 *   hk-market 行情页要全量列表 → 前端常量最直接。阶段四接全市场榜单(MarketHomePage)后改走 API。
 * 红线:港股只读 · 行情展示 · 不下单不接 AI(阶段二)。
 */

export interface HkPoolItem {
  symbol: string
  name: string
  sector: string
}

export const HK_POOL: readonly HkPoolItem[] = [
  // 科技 / 互联网
  { symbol: '00700', name: '腾讯控股', sector: '科技' },
  { symbol: '09988', name: '阿里巴巴-W', sector: '科技' },
  { symbol: '03690', name: '美团-W', sector: '科技' },
  { symbol: '01810', name: '小米集团-W', sector: '科技' },
  { symbol: '09618', name: '京东集团-SW', sector: '科技' },
  { symbol: '01024', name: '快手-W', sector: '科技' },
  { symbol: '09999', name: '网易-S', sector: '科技' },
  { symbol: '09888', name: '百度集团-SW', sector: '科技' },
  // 金融
  { symbol: '00388', name: '香港交易所', sector: '金融' },
  { symbol: '01299', name: '友邦保险', sector: '金融' },
  { symbol: '00005', name: '汇丰控股', sector: '金融' },
  { symbol: '00939', name: '建设银行', sector: '金融' },
  { symbol: '01398', name: '工商银行', sector: '金融' },
  { symbol: '02318', name: '中国平安', sector: '金融' },
  // 电信 / 汽车
  { symbol: '00941', name: '中国移动', sector: '电信' },
  { symbol: '01211', name: '比亚迪股份', sector: '汽车' },
  { symbol: '02015', name: '理想汽车-W', sector: '汽车' },
  { symbol: '09868', name: '小鹏汽车-W', sector: '汽车' },
] as const
