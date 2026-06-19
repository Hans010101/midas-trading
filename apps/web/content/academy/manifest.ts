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
  { slug: "contract", name: "合约与衍生品", stageLabel: "第四阶", desc: "加密核心战场:永续合约、资金费率、保证金模式、爆仓与强平机制,以及 OI / 多空比 / 基差等合约数据与风险防范。全程虚拟,教学内容仅供学习参考。" },
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
  { slug: "C1-1", stage: "chan", order: 10, title: "线段的划分与两种破坏", file: "C1-1.md", excerpt: "入门阶段我们说过：线段至少由连续三笔构成、且要有重叠。但一到实战，真正折磨人的不是“什么是线段”，而是——这一段到底走完了没有、在哪里结束？…" },
  { slug: "C1-2", stage: "chan", order: 11, title: "中枢的扩展与延伸", file: "C1-2.md", excerpt: "入门里中枢是“至少三段次级别走势重叠出来的区间”。但中枢形成后走势往往不会乖乖结束、而会继续折腾——最常被搞混的就是延伸和扩展（还有近亲扩张）。…" },
  { slug: "C1-3", stage: "chan", order: 12, title: "中枢级别的升级", file: "C1-3.md", excerpt: "上一篇讲了中枢的延伸、扩展、扩张，反复提到一个词：升级。这一篇把“升级”讲透——一个低级别中枢，是怎么一步步变成高级别中枢的？级别提升靠什么判定？…" },
  { slug: "C1-4", stage: "chan", order: 13, title: "走势类型的判定", file: "C1-4.md", excerpt: "“这是上涨还是震荡？”几乎是所有分析的起点。普通技术分析靠“看着像”，而缠论给了一个用中枢数量就能精确判定的标准——严格区分趋势与盘整。…" },
  { slug: "C1-5", stage: "chan", order: 14, title: "三类买卖点的实战识别与常见误判", file: "C1-5.md", excerpt: "入门里我们记住了三类买卖点的“定义”。但实战中光会背没用——真正难的是：在一张还没走完的图上怎么把它们认出来？又最容易把什么错当成它们？…" },
  { slug: "C1-6", stage: "chan", order: 15, title: "买卖点的级别问题", file: "C1-6.md", excerpt: "很多人学会了找三类买卖点，却还是做不好。一个高频原因是：搞错了买卖点的“级别”。同样叫“第一类买点”，日线的和 5 分钟的分量天差地别。…" },
  { slug: "C1-7", stage: "chan", order: 16, title: "背驰的精确判断", file: "C1-7.md", excerpt: "背驰，是缠论买卖点（尤其 1 买 / 1 卖）的“发动机”——没有背驰就没有趋势的转折，但它也最容易判错。讲清怎么用 MACD 黄白线 + 红绿柱面积来判断背驰。…" },
  { slug: "C1-8", stage: "chan", order: 17, title: "第二三类买卖点的组合运用", file: "C1-8.md", excerpt: "前面逐类讲了三类买卖点（C1-5）和它们的级别（C1-6）。实战中它们很少单独登场，更常见的是几类前后衔接、相互印证——专讲第二、三类买卖点怎么搭配着看。…" },
  { slug: "C1-9", stage: "chan", order: 18, title: "级别的概念与递归及大小级别联立", file: "C1-9.md", excerpt: "“级别”是缠论的灵魂，也是最容易被误解的概念——很多人直接把它当成“1 分钟、5 分钟、日线”，越用越乱。把级别是什么、怎么递归定义与大小级别联立一次讲清。…" },
  { slug: "C1-10", stage: "chan", order: 19, title: "级别共振", file: "C1-10.md", excerpt: "上一篇讲了大小级别联立。这一篇讲一个更进一步、也更诱人的概念——级别共振：多个级别在同一方向上“撞到一起”时意味着什么、怎么用、又最容易在哪里翻车。…" },
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
  { slug: "F19", stage: "system", order: 19, title: "把策略搬上合约:杠杆先改变了什么", file: "F19.md", excerpt: "合约不是「高级现货」而是风险结构完全不同的工具;杠杆带来双向放大盈亏、爆仓、资金费、多空双向四个本质变化。" },
  { slug: "F20", stage: "system", order: 20, title: "合约里的趋势与突破:顺势加杠杆的机会与代价", file: "F20.md", excerpt: "做多三价关系:开仓价>止损价>爆仓价;杠杆越高爆仓价越近、容错越小,易在正常回调里被扫损/爆仓。" },
  { slug: "F21", stage: "system", order: 21, title: "资金费率套利:原理、方向,以及为什么「套利」不等于无风险", file: "F21.md", excerpt: "现货+合约对冲只吃费率(delta中性);但套利绝非无风险——基差/爆仓/费率反向/成本/流动性五大风险。" },
  { slug: "F22", stage: "system", order: 22, title: "用合约对冲与套保:给持仓上「保险」的基础思路", file: "F22.md", excerpt: "用合约空单给现货上保险(套保);对冲降低方向风险、不消除所有风险,有资金费/机会成本/合约腿爆仓等代价。" },
  { slug: "F23", stage: "system", order: 23, title: "合约的仓位与风险管理:杠杆下怎么用 1% 风险法 + 防爆仓", file: "F23.md", excerpt: "名义敞口(=保证金×杠杆)≠保证金占用、盈亏按敞口算;1%风险法搬合约,止损必须在爆仓价之前否则失效。" },
  { slug: "F24", stage: "system", order: 24, title: "合约实战的常见错误与陷阱", file: "F24.md", excerpt: "五大常见错误:满仓高杠杆/扛单不止损/忽视资金费/频繁开平/把合约当赌场——合约放大的是「错误的代价」。" },
  { slug: "F25", stage: "system", order: 25, title: "怎么做案例复盘:方法,而不是抄作业", file: "F25.md", excerpt: "案例学的是方法不是抄答案;站在「当时」视角拆客观结构/可行应对/过程对错,讲过去不指导现在、不预测。" },
  { slug: "F26", stage: "system", order: 26, title: "一笔趋势交易的完整复盘(方法演示)", file: "F26.md", excerpt: "示意案例完整演示一笔趋势交易(识别→回调进场→移动止损→反转离场→复盘);是流程演示、非必然成功的剧本。" },
  { slug: "F27", stage: "system", order: 27, title: "一笔失败交易的复盘:从亏损里学什么", file: "F27.md", excerpt: "示意案例复盘一笔失败交易(逆势抄底+扛单);拆判断错vs执行错、对事不对结果,失败只讲教训不羞辱。" },
  { slug: "F28", stage: "system", order: 28, title: "把体系跑通:一个案例里的六模块协作", file: "F28.md", excerpt: "一笔像样的交易是六模块协同的结果(缺一则崩、取决于最弱一环);呼应适合自己+检验迭代,体系非稳赚、敬畏第一。" },
  { slug: "F29", stage: "system", order: 29, title: "点金能帮你练什么:虚拟环境的价值", file: "F29.md", excerpt: "交易是实践技能,需要「能犯错但不付真实代价」的练习场;点金能练分析/执行/心态/复盘,但虚拟≠真实、练得好≠能赚、它是工具不是稳赚体系。" },
  { slug: "F30", stage: "system", order: 30, title: "用 K 线 / 指标 / 缠论看懂结构", file: "F30.md", excerpt: "分层读结构(大方向→关键位→动能→缠论细节);多工具叠加交叉印证,但印证只提高把握不消除误判,工具是参考、不是买卖指令。" },
  { slug: "F31", stage: "system", order: 31, title: "用虚拟交易练执行与纪律", file: "F31.md", excerpt: "纪律靠反复练成肌肉记忆;用虚拟交易练执行链条、把扛单/乱止盈等错零成本犯在虚拟里再改;但虚拟缺真实资金压力,虚拟成绩不代表真实。" },
  { slug: "F32", stage: "system", order: 32, title: "AI 决策卡怎么用:把它当参考,不当指令", file: "F32.md", excerpt: "AI 决策卡是会犯错的参考视角、不是荐股/买卖指令;先有自己判断再与 AI 对照,理解原理+独立判断重于照搬;必带免责、不能单独依赖。" },
  { slug: "F33", stage: "system", order: 33, title: "用策略研究室回测打磨规则", file: "F33.md", excerpt: "想法→规则化→回测→读指标(重最大回撤/盈亏比)→迭代;★回测有效≠未来有效,警惕过拟合/幸存者偏差,回测是淘汰烂策略而非证明能赚。" },
  { slug: "F34", stage: "system", order: 34, title: "从模拟到形成自己的方法:一条练习路径", file: "F34.md", excerpt: "观察→小规模虚拟试→复盘→调整→形成稳定可执行的打法;目标是「适合自己+能稳定执行」而非最强策略(没有圣杯),形成的是方法非稳赚公式。" },
  { slug: "F35", stage: "system", order: 35, title: "在点金完整跑一遍交易流程(知行合一)", file: "F35.md", excerpt: "七环节完整流程(分析→计划→虚拟进场→风险仓位→虚拟出场→复盘→回测)串成「学→用」闭环;全程虚拟、不构成建议,帮你练熟流程、不替你保证结果。" },
  { slug: "F36", stage: "system", order: 36, title: "回顾:从入门到体系,你学了什么", file: "F36.md", excerpt: "五阶学习路径回顾(A入门→B技术→C缠论→E合约→F体系实战);前四阶认识、第五阶组织运用;★学完≠会赚钱,真正决定长期的是执行/纪律/风控/复盘/敬畏。" },
  { slug: "F37", stage: "system", order: 37, title: "成长心态:亏损、进步与对市场的敬畏", file: "F37.md", excerpt: "正确看待亏损(过程对的亏可接受vs过程错的亏必须改)、进步靠复盘迭代(慢就是快)、对市场永远敬畏;★反对速成暴富,追求长期稳健活下来。" },
  { slug: "F38", stage: "system", order: 38, title: "长期主义:把交易当成一场持续修炼", file: "F38.md", excerpt: "交易是长期持续的修炼;靠体系活下来/纪律执行/复盘进步/风控保命四根支柱;长期主义 vs 短期赌博——活得久是最大的优势(全训练营收尾)。" },
  { slug: "E1", stage: "contract", order: 1, title: "永续合约是什么:没有到期日的合约", file: "E1.md", excerpt: "永续合约 = 没有到期日、可长期持有的合约,加密最主流;靠资金费率锚定现货;带杠杆双向放大盈亏、有爆仓风险,是高风险工具。" },
  { slug: "E2", stage: "contract", order: 2, title: "资金费率:永续合约的锚", file: "E2.md", excerpt: "资金费率是多空之间定期收付的费用(正费率多头付空头/负费率空头付多头),让永续价锚定现货;是情绪参考、不预测,也是持有成本。" },
  { slug: "E3", stage: "contract", order: 3, title: "保证金模式:全仓与逐仓", file: "E3.md", excerpt: "全仓(账户全部余额兜底)vs 逐仓(每仓独立保证金);选择只改变风险分布、不消除爆仓风险,都需谨慎配合控制杠杆与仓位。" },
  { slug: "E4", stage: "contract", order: 4, title: "爆仓价是怎么算的:强平机制", file: "E4.md", excerpt: "爆仓价 = 价格反向触及时被强平的价格;多单在开仓价下方、空单在上方;杠杆越高爆仓价越近,维持保证金率致实际爆仓常比理论更早。" },
  { slug: "E5", stage: "contract", order: 5, title: "持仓量(OI):合约市场的资金温度计", file: "E5.md", excerpt: "持仓量 OI = 尚未平仓的合约总量(存量);增仓 = 新资金进场、减仓 = 资金离场;与价格配合是参考解读、有例外、不预测。" },
  { slug: "E6", stage: "contract", order: 6, title: "多空比:市场情绪的参考", file: "E6.md", excerpt: "多空比 = 做多与做空力量的比例,有大户/账户数等不同口径;不是\"多头多就一定涨\",是情绪参考、不是信号、不预测。" },
  { slug: "E7", stage: "contract", order: 7, title: "基差与价差:永续与现货的价格关系", file: "E7.md", excerpt: "基差 = 永续价 − 现货价(正基差升水/负基差贴水);与资金费率方向高度相关,是参考数据、不预测价格。" },
  { slug: "E8", stage: "contract", order: 8, title: "合约的风险:为什么说合约是把双刃剑", file: "E8.md", excerpt: "合约是高风险工具,风险叠加(杠杆双向放大/爆仓本金可能归零/资金费成本/高波动),还放大情绪行为风险;风险管理是生死线。" },
  { slug: "E9", stage: "contract", order: 9, title: "合约交易中的爆仓预防", file: "E9.md", excerpt: "爆仓预防:控制杠杆(低杠杆起步)+ 止损(设在爆仓价之前)+ 控仓 + 留足保证金 + 管情绪;没有方法保证不爆仓,降低风险≠消除风险。" },
  { slug: "E10", stage: "contract", order: 10, title: "点金的合约分析:在虚拟环境里理解合约市场", file: "E10.md", excerpt: "点金是全程虚拟分析终端,以永续为主,提供 K 线指标/缠论/合约维度(OI/多空比/资金费率)/AI 决策卡;AI 仅供参考、不构成投资建议、不预测。" },
];
