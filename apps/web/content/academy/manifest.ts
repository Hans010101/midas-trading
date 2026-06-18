// 训练营内容清单 — 自动生成,前端读此文件生成列表/导航
// 文章正文在 content/academy/articles/{slug}.md,配图在 public/academy-img/

export interface AcademyStage {
  slug: string;       // 'basics' | 'technical' | 'chan'
  name: string;       // '入门筑基'
  stageLabel: string; // '第一阶'
  desc: string;
}

export interface AcademyArticle {
  slug: string;    // 'A2'
  stage: string;   // 'basics'
  order: number;
  title: string;
  file: string;    // 'A2.md'
  excerpt: string;
}

export const ACADEMY_STAGES: AcademyStage[] = [
  { slug: "basics", name: "入门筑基", stageLabel: "第一阶", desc: "从零认识交易：K线、做多做空、杠杆、支撑阻力、四大市场、虚拟交易。" },
  { slug: "technical", name: "技术分析", stageLabel: "第二阶", desc: "经典技术指标：均线、金叉死叉、MACD、布林带、RSI。" },
  { slug: "chan", name: "缠论专题", stageLabel: "第三阶", desc: "缠论结构化分析：包含关系、分型、笔、线段、中枢、三类买卖点。" },
  { slug: "system", name: "交易体系与实战", stageLabel: "第五阶", desc: "把前四阶的 K 线、指标、缠论、合约整合成完整交易体系——涵盖交易计划、风险与仓位、心理、纪律、复盘,以及趋势 / 震荡两类实战框架。教学内容仅供学习参考。" },
];

export const ACADEMY_ARTICLES: AcademyArticle[] = [
  { slug: "A2", stage: "basics", order: 1, title: "K线是什么、怎么读懂它", file: "A2.md", excerpt: "K线（也叫蜡烛图）是市场上最常用的价格图表形式。它的样子像一根蜡烛——中间一个粗的\"身体\"，上下可能各伸出一条细细的\"芯…" },
  { slug: "A3", stage: "basics", order: 2, title: "K线的影线告诉你什么", file: "A3.md", excerpt: "上一篇我们认识了K线的\"实体\"和\"影线\"。实体讲的是开盘到收盘的结果，而影线，记录的是这段时间里价格冲到过、又没能守住的…" },
  { slug: "A4", stage: "basics", order: 3, title: "做多与做空：双向都能赚钱", file: "A4.md", excerpt: "很多新手对交易的第一印象是：\"买入，然后等它涨，涨了卖掉赚钱。\"这没错，但这只是一半。" },
  { slug: "A5", stage: "basics", order: 4, title: "杠杆是什么：放大盈亏的双刃剑", file: "A5.md", excerpt: "\"杠杆\"这个词来自物理学——用一根杠杆，能用小的力撬起重的东西。在交易里，杠杆的意思类似：用一笔较小的本金，去操作一笔比…" },
  { slug: "A6", stage: "basics", order: 5, title: "什么是支撑位和阻力位", file: "A6.md", excerpt: "价格在图上不是漫无目的地乱走的。它常常在某些位置\"卡住\"——跌到某个价位附近就跌不动了，像踩到了地板；涨到某个价位附近就…" },
  { slug: "A7", stage: "basics", order: 6, title: "趋势是什么：交易者最好的朋友", file: "A7.md", excerpt: "如果你盯着一段K线看久了，会发现价格虽然上上下下，但常常呈现出一个整体的\"方向感\"——要么重心一路往上挪，要么一路往下沉…" },
  { slug: "A8", stage: "basics", order: 7, title: "市价单 vs 限价单：怎么下单", file: "A8.md", excerpt: "当你决定买入或卖出时，要通过\"下单\"告诉市场你的意图。但下单不是只有一种方式——最基础、最常用的两种是市价单和限价单。" },
  { slug: "A9", stage: "basics", order: 8, title: "止损与止盈：保护本金的纪律", file: "A9.md", excerpt: "很多新手把所有精力放在\"什么时候买\"，却很少认真想过\"什么时候卖、尤其是看错了怎么办\"。但成熟交易者都明白：离场计划，往…" },
  { slug: "A10", stage: "basics", order: 9, title: "加密、美股、A股、港股有什么不同", file: "A10.md", excerpt: "加密货币、美股、A股、港股，是很多人最常接触的四类市场，也正是点金覆盖的四大市场。它们都遵循\"价格由供需决定\"的基本逻辑…" },
  { slug: "A11", stage: "basics", order: 10, title: "现货与合约：点金加密为什么以合约为主", file: "A11.md", excerpt: "在加密市场里，\"参与一个币的行情\"主要有两条路：买现货，或者做合约。这两者看起来都和价格涨跌挂钩，但底层机制、风险、能做…" },
  { slug: "A12", stage: "basics", order: 11, title: "什么是虚拟交易：零风险练手", file: "A12.md", excerpt: "学开车的人，几乎都先在驾校场地或模拟器上练过，没人第一天就开上高速。交易也一样——虚拟交易，就是交易世界里的\"模拟器\"。" },
  { slug: "B1", stage: "technical", order: 1, title: "均线（MA）：最基础的趋势指标", file: "B1.md", excerpt: "K 线一根一根看，价格上上下下、很难一眼看出方向。有没有办法把这些杂乱的波动\"抚平\"一些，让趋势更清楚？均线（MA，Mo…" },
  { slug: "B2", stage: "technical", order: 2, title: "均线的金叉与死叉", file: "B2.md", excerpt: "上一篇我们知道，不同周期的均线性格不同：短期均线灵敏、长期均线稳定。当我们把一条短期均线和一条长期均线放在一起，它们会时…" },
  { slug: "B3", stage: "technical", order: 3, title: "多均线系统：多头排列与空头排列", file: "B3.md", excerpt: "前面我们用的是一条或两条均线。实际中，很多交易者会同时挂上短期、中期、长期好几条均线——这就是\"多均线系统\"。" },
  { slug: "B4", stage: "technical", order: 4, title: "MACD 指标：原理与构成", file: "B4.md", excerpt: "均线能看趋势方向，但有个不足：它主要告诉你\"涨还是跌\"，不太能体现\"涨跌的劲头（动能）有多强、是在加速还是在衰竭\"。MA…" },
  { slug: "B5", stage: "technical", order: 5, title: "MACD 的金叉、死叉与柱状图", file: "B5.md", excerpt: "上一篇我们拆解了 MACD 的构成：DIF 线（快线）、DEA 线（慢线）、红绿柱（柱 = DIF − DEA）。这一篇…" },
  { slug: "B6", stage: "technical", order: 6, title: "MACD 背离：趋势衰竭的信号", file: "B6.md", excerpt: "通常情况下，价格创新高，反映动能的指标也会跟着创新高——两者方向一致，趋势是\"健康\"的。但有时会出现一种耐人寻味的情况：…" },
  { slug: "B7", stage: "technical", order: 7, title: "布林带（BOLL）：波动的通道", file: "B7.md", excerpt: "前面学的均线，是一条线。布林带（BOLL，Bollinger Bands）则更进一步——它在均线的基础上，给价格画出一条…" },
  { slug: "B8", stage: "technical", order: 8, title: "布林带的开口与收口", file: "B8.md", excerpt: "上一篇我们知道，布林带的上下轨是按\"中轨 ± 标准差\"画的，而标准差反映波动——所以通道的宽窄，直接对应着市场波动的大小…" },
  { slug: "B9", stage: "technical", order: 9, title: "RSI 指标：超买与超卖", file: "B9.md", excerpt: "前面学的 MACD、布林带，都基于价格的均线和波动。RSI（相对强弱指标，Relative Strength Index…" },
  { slug: "C1", stage: "chan", order: 1, title: "缠论是什么：一套完整的市场分析体系", file: "C1.md", excerpt: "学到这里，你已经认识了均线、MACD、布林带、RSI 等技术指标。它们大多是\"在价格之上叠加一个计算值\"来辅助判断。而缠…" },
  { slug: "C2", stage: "chan", order: 2, title: "学缠论前：摆正心态（不神化、不迷信）", file: "C2.md", excerpt: "在真正进入分型、笔、中枢这些概念之前，有一篇\"务虚\"但极其重要的内容必须先讲——学缠论的心态。" },
  { slug: "C3", stage: "chan", order: 3, title: "K线的包含关系：缠论的第一步", file: "C3.md", excerpt: "缠论要在 K 线上识别分型、画笔，但原始的 K 线常常杂乱——有些 K 线被相邻 K 线完全\"包住\"，让结构看起来模糊不…" },
  { slug: "C4", stage: "chan", order: 4, title: "分型：顶分型与底分型", file: "C4.md", excerpt: "处理完 K 线的包含关系后，K 线序列变干净了。接下来，缠论要在这干净的序列上，找出局部的顶和底——这就是分型。" },
  { slug: "C5", stage: "chan", order: 5, title: "笔：连接分型的基本单位", file: "C5.md", excerpt: "上一篇我们学会了在 K 线序列上识别顶分型和底分型。这些分型是一个个孤立的\"局部转折点\"，而笔，就是把相邻的顶分型和底分…" },
  { slug: "C6", stage: "chan", order: 6, title: "线段：比笔更高一级的走势单位", file: "C6.md", excerpt: "上一篇我们学会了画笔。但笔有个问题：它比较细碎。市场稍微一波动，就可能形成一笔，单看笔，走势显得零零碎碎、不够稳定。" },
  { slug: "C7", stage: "chan", order: 7, title: "中枢：缠论的核心概念", file: "C7.md", excerpt: "如果说分型、笔、线段是缠论的\"骨架\"，那么中枢就是缠论的\"心脏\"——它是整个体系里最核心、也最难的概念。后面要讲的买卖点…" },
  { slug: "C8", stage: "chan", order: 8, title: "缠论的三类买卖点", file: "C8.md", excerpt: "在讲\"买卖点\"之前，有一句话必须先说清楚，而且贯穿全篇：" },
  { slug: "C9", stage: "chan", order: 9, title: "缠论怎么用、怎么不被它误导", file: "C9.md", excerpt: "走到这里，缠论专题的核心概念——包含关系、分型、笔、线段、中枢、买卖点——你已经都认识了。但学会概念，和正确地使用它，是…" },
  { slug: "F1", stage: "system", order: 1, title: "什么是交易体系:从零散知识到完整系统", file: "F1.md", excerpt: "把 K 线、指标、缠论、合约等零散工具,整合成一套可重复执行的完整交易规则。" },
  { slug: "F2", stage: "system", order: 2, title: "交易计划:每一笔交易前该想清楚什么", file: "F2.md", excerpt: "先计划后交易——进场前定好理由、止损、目标、仓位,用事前理性对抗持仓情绪。" },
  { slug: "F3", stage: "system", order: 3, title: "风险回报比:为什么不能只看胜率", file: "F3.md", excerpt: "盈亏比与胜率配合,才决定一个方法长期是赚是亏;高胜率也可能亏钱。" },
  { slug: "F4", stage: "system", order: 4, title: "仓位管理:决定你能在市场活多久", file: "F4.md", excerpt: "固定比例风险法与「仓位 = 风险金额 ÷ 止损幅度」,让单笔亏损恒定可控。" },
  { slug: "F5", stage: "system", order: 5, title: "交易心理:认识你的情绪敌人", file: "F5.md", excerpt: "恐惧、贪婪、希望、后悔四大情绪陷阱,以及它们如何让人做出错误决策。" },
  { slug: "F6", stage: "system", order: 6, title: "纪律与执行:知道和做到之间的鸿沟", file: "F6.md", excerpt: "为什么道理都懂却做不到,以及如何用规则与纪律真正落地执行。" },
  { slug: "F7", stage: "system", order: 7, title: "复盘:从每一笔交易中学习", file: "F7.md", excerpt: "看过程对错而非单次盈亏——最危险的是「做错却赚钱」,最该坚持的是「做对却亏钱」。" },
  { slug: "F8", stage: "system", order: 8, title: "趋势交易体系:顺势而为的完整框架", file: "F8.md", excerpt: "识别趋势、回调进场、跌破离场、让利润奔跑;趋势行情好、震荡行情易反复止损。" },
  { slug: "F9", stage: "system", order: 9, title: "震荡交易体系:区间里的高抛低吸", file: "F9.md", excerpt: "区间内高抛低吸的框架,以及假突破、趋势启动被套两大风险与严格止损。" },
  { slug: "F10", stage: "system", order: 10, title: "构建适合自己的交易体系", file: "F10.md", excerpt: "没有最好只有适合自己的体系:从模仿到原创,并用回测与虚拟实盘检验迭代。" },
  { slug: "F11", stage: "system", order: 11, title: "交易策略概览:你有哪些「打法」", file: "F11.md", excerpt: "交易策略 = 体系里「分析方法 + 进出场规则」的实现;按趋势/震荡、顺势/逆势、左侧/右侧分类,没有最好只有适配。" },
  { slug: "F12", stage: "system", order: 12, title: "趋势跟踪策略:让利润奔跑", file: "F12.md", excerpt: "只顺势不预测顶底、移动止损让利润奔跑;胜率往往不高、盈利集中在少数大趋势(附海龟法则的历史警示)。" },
  { slug: "F13", stage: "system", order: 13, title: "突破交易策略:关键位变盘进场", file: "F13.md", excerpt: "关键位突破时顺势进场;最大敌人是假突破,用放量/收盘/回踩提高确认,但无法 100% 排除。" },
  { slug: "F14", stage: "system", order: 14, title: "均值回归策略:价格回归常态", file: "F14.md", excerpt: "价格过度偏离均值后倾向回归;致命前提是必须真震荡,趋势中逆势会被一路碾压。" },
  { slug: "F15", stage: "system", order: 15, title: "网格交易:震荡套利的双刃剑", file: "F15.md", excerpt: "区间内分层高抛低吸,绝非躺赚;单边行情越套越深或踏空、加杠杆可能爆仓(附马丁格尔强警示)。" },
  { slug: "F16", stage: "system", order: 16, title: "左侧交易 vs 右侧交易", file: "F16.md", excerpt: "左侧(拐点前埋伏/抄底)vs 右侧(确认后追随);没有方法精确抄底逃顶,新手右侧更安全。" },
  { slug: "F17", stage: "system", order: 17, title: "没有圣杯:策略与市场环境匹配", file: "F17.md", excerpt: "没有能全天候有效的策略;核心能力是识别行情、用对策略、靠完整体系活下来。" },
  { slug: "F18", stage: "system", order: 18, title: "用策略研究室回测验证你的策略", file: "F18.md", excerpt: "把想法变成可量化规则,用策略研究室回测 + 虚拟验证;回测有效≠未来有效(过拟合/幸存者偏差)。" },
];
