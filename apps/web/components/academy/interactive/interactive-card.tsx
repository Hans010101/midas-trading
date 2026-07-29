'use client'

import { type ReactNode } from 'react'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'

const ENGLISH_COPY: Record<string, string> = {
  '布林带:上下轨对称': 'Bollinger Bands: Symmetric Envelopes',
  '拖标准差倍数 K,看上下轨相对中轨对称张缩。中轨 = MA20。':
    'Adjust the standard-deviation multiplier and see both bands expand symmetrically around MA20.',
  'K线合并(缠论包含处理)': 'Candlestick Inclusion in Chan Theory',
  '两根有包含关系的 K 线,切换处理方向:向上取「高高」、向下取「低低」。':
    'Resolve two inclusive candles by switching between upward and downward processing.',
  '一根 K 线是怎么构成的': 'Anatomy of a Candlestick',
  '拖动 开 / 高 / 低 / 收 四个点,看实体与上下影线怎么变;或点预设切换阳线 / 阴线 / 十字星。':
    'Drag open, high, low, and close to see how the body and wicks change, or choose a preset candle.',
  '爆仓价随杠杆移动': 'How Leverage Moves the Liquidation Price',
  '开仓价固定为 100。拖动杠杆滑块、切换多空,看爆仓价线怎么移动。':
    'Keep entry fixed at 100, then change leverage and direction to see the liquidation threshold move.',
  'RSI 与钝化': 'RSI and Indicator Saturation',
  '拖趋势强度,看强趋势中 RSI 长期贴在超买/超卖区钝化、不翻转。':
    'Increase trend strength to see why RSI can remain overbought or oversold without reversing.',
  '盈亏比与期望': 'Risk–Reward and Expectancy',
  '拖止盈距离、止损距离、胜率,看盈亏比与期望联动。高盈亏比可容忍低胜率。':
    'Adjust target, stop, and win rate to see how risk–reward changes expected value.',
  '缠论中枢怎么形成': 'How a Chan Theory Central Hub Forms',
  '拖动三段走势各自的高点 / 低点(共 6 个点),看上沿 ZG、下沿 ZD 怎么算、三段有没有共同重叠区。':
    'Move the highs and lows of three Segments to calculate ZG, ZD, and their shared overlap.',
  '趋势与震荡': 'Trend vs. Range',
  '切换三种市态,看摆动高低点的结构差别。不同市态需要不同应对。':
    'Compare swing structure across uptrends, downtrends, and range-bound markets.',
  '1%风险法:杠杆不决定单笔亏损': 'The 1% Risk Rule: Size Defines Loss',
  '盈亏按名义敞口算,不是按保证金': 'PnL Follows Notional Exposure',
  'MACD 金叉(DIF 上穿 DEA)': 'MACD Golden Cross',
  '固定参数 EMA12 / EMA26 / DEA9。DIF 上穿 DEA = 金叉、下穿 = 死叉;柱 = (DIF − DEA) × 2。':
    'Using EMA12, EMA26, and DEA9, inspect signal-line crossovers and histogram changes.',
  '均线金叉 / 死叉': 'Moving-Average Crossovers',
  '拖短均线周期,看短均线上穿长均线(金叉)、下穿(死叉)。长均线固定 MA20。':
    'Change the fast MA period and watch it cross above or below the fixed MA20.',
  '马丁格尔(反面演示)': 'Martingale: A Failure Scenario',
  '亏损后加倍下注,下注额指数膨胀。拖连亏次数,看累计投入冲破本金、爆仓归零。':
    'Extend the losing streak to see position size grow exponentially and exhaust finite capital.',
  '全仓 vs 逐仓': 'Cross vs. Isolated Margin',
  '爆仓是一步步逼近的': 'The Path to Liquidation',
  '多单、开仓价 100。点「再跌一格」让价格下跌,看保证金怎么被一格格吃掉、强平在哪一步触发。':
    'Step a long position down from an entry of 100 and watch margin erode until liquidation.',
  '网格交易': 'Grid Trading',
  '切换市态看网格命运:震荡市来回穿格赚价差,单边下跌只买不卖、逐格套牢。':
    'Compare how a grid behaves in a range versus a one-way decline.',
  'KDJ:K / D / J 三线': 'KDJ: The K, D, and J Lines',
  '拖趋势强度,看 K 上穿 D(金叉)、超买超卖区与钝化;J 最敏感、可冲出 0~100。固定参数 (9,3,3)。':
    'Adjust trend strength to inspect K/D crossovers, saturation, and the more sensitive J line.',
  '资金费率:谁付谁': 'Funding Rate: Who Pays Whom',
  '买卖点(缠论)': 'Chan Theory Buy and Sell Points',
  '一二三类买点的结构位置;卖点对称。这是结构描述,不是买卖指令。':
    'Explore the structural locations of Type 1, 2, and 3 points and their mirrored sell-side forms.',
  '背驰(缠论)': 'Divergence in Chan Theory',
  '价格创新高但 MACD 力度未同步创新高 = 顶背驰。切换看背驰 / 不背驰。':
    'Compare a new price high with weakening versus strengthening MACD momentum.',
  '分型与笔(缠论)': 'Fractals and Strokes in Chan Theory',
  '顶分型=中间K高低点都最高,底分型=都最低,顶底交替连成笔。换一组看不同结构。':
    'Identify Top and Bottom Fractals, then connect alternating pivots into Strokes.',
}

/**
 * D 系列交互组件统一外壳:暖米白卡片 + 衬线标题 + 红竖标 + 统一免责小字。
 * ⛔ 教学页面不挂 VIRTUAL 徽章(红线);用「互动演示」标签区分。
 */
export function InteractiveCard({
  title,
  subtitle,
  children,
  footnote,
}: {
  title: string
  subtitle?: string
  children: ReactNode
  footnote?: string
}) {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const localizedTitle = en ? (ENGLISH_COPY[title] ?? title) : title
  const localizedSubtitle = en && subtitle ? (ENGLISH_COPY[subtitle] ?? subtitle) : subtitle
  return (
    <figure className="my-8 overflow-hidden rounded-lg border border-paper bg-surface-card shadow-sm">
      <figcaption className="border-b border-paper bg-surface-subtle/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-block h-3.5 w-1 rounded-sm bg-midas-red" aria-hidden />
          <span className="font-serif text-base font-bold text-foreground">{localizedTitle}</span>
          <span className="ml-auto shrink-0 rounded bg-gold/15 px-1.5 py-0.5 text-[10px] font-medium text-gold">
            {en ? 'Interactive' : '互动演示'}
          </span>
        </div>
        {localizedSubtitle ? (
          <p className="mt-1.5 text-xs leading-relaxed text-foreground/60">{localizedSubtitle}</p>
        ) : null}
      </figcaption>
      <div className="px-3 py-4 sm:px-4">{children}</div>
      <p className="border-t border-paper px-4 py-2 text-[11px] leading-relaxed text-foreground/50">
        {en ? 'Interactive learning example' : (footnote ?? '示意演示 · 数据为教学示例')}
      </p>
    </figure>
  )
}
