/**
 * 关于点金(SEO 批4 · GEO 内容件 · 审计批4① + D6 定案)。
 *
 * 定位:把现有合规免责体系升格为「可引用的原则页」= E-E-A-T 信任信号(合规即 SEO 资产)。
 * D6:只写产品与方法论,不披露运营主体(匿名延续)。文案经产品负责人核定后照搬不改。
 * ★红线:非终端页(允许出现「虚拟/模拟」)· 无买卖祈使词 · 免责措辞与 /risk 同源。
 * title 用短版:批1 的 layout title.template('%s · 点金 Midas')合并后自动拼品牌后缀。
 */

import { LegalH2, LegalP, LegalPage } from '@/components/legal/legal-page'
import { JsonLd } from '@/components/seo/json-ld'
import { organizationSchema } from '@/lib/seo/schema'

export const dynamic = 'force-static'

export const metadata = {
  title: '关于点金',
  description:
    '点金 Midas 是 AI 原生的跨市场(加密/美股/A股/港股)分析与交易学习终端:全程虚拟资金、不构成投资建议。这里是我们的产品定位、方法论与六条产品原则。',
  // SEO 批3(点金-3 叠加·衔接点):canonical
  alternates: {
    canonical: '/about',
    languages: { 'zh-CN': '/about', en: '/en/about', 'x-default': '/about' },
  },
  openGraph: { title: '关于 Midas Trading', url: '/about' },
}

export default function AboutPage() {
  return (
    <LegalPage title="关于点金">
      {/* SEO 批3:Organization JSON-LD(与 landing 同 @id · 让知识图谱把 about 归入品牌实体)*/}
      <JsonLd data={organizationSchema} />
      <LegalP>
        Midas Trading 是一款独立运行于 Cloudflare 的 AI
        原生跨市场分析与交易学习终端,覆盖加密货币、
        美股、A股与港股四大市场。我们把行情数据、技术指标、缠论结构、合约数据与 AI
        分析整合在一个终端里,并配套一套免费公开的系统化交易教学内容——训练营六阶教学文章与
        交易名词词典。
      </LegalP>
      <LegalP>
        点金上的一切交易都使用虚拟资金:不涉及任何真实货币、真实证券或真实数字资产的买卖,
        也永远不会接入真实交易通道。这不是一条运营口径,而是产品的底层设计。
      </LegalP>

      <LegalH2>我们的方法论:描述结构,而非预测价格</LegalH2>
      <LegalP>
        市场分析工具最常见的越界,是把「分析」悄悄做成「指令」。点金的做法相反:所有 AI
        输出——决策卡、结构诊断、策略信号、缠论标注——都是对当前市场结构的描述性参考:
        多空力量如何分布、价格处在什么结构位置、哪些指标出现了什么状态。它们不是对未来价格
        走势的预测,更不是操作指引。判断,永远留给使用者自己。
      </LegalP>
      <LegalP>
        教学内容遵循同一逻辑:训练营从 K 线与市场规则讲到指标、缠论、合约机制与交易体系,
        目标是让学习者理解原理、建立自己的分析框架,而不是提供任何「照做就能赢」的信号。
        我们在讲到马丁格尔等高风险策略时,重点恰恰是它为什么危险。
      </LegalP>

      <LegalH2>六条产品原则</LegalH2>
      <LegalP>1. 全程虚拟:所有交易均为虚拟资金模拟,永不接入真实下单通道。</LegalP>
      <LegalP>
        2. 不构成投资建议:所有 AI 分析、策略信号与教学内容仅供学习参考,均强制附带免责声明;
        不预测价格、不保证盈利。
      </LegalP>
      <LegalP>
        3. 描述结构而非预测价格:AI 输出限定为对市场结构的客观描述,系统层面拦截操作性
        祈使表述。
      </LegalP>
      <LegalP>
        4. 教学免费公开:训练营全部文章与名词词典无付费墙、无登录墙,任何人可读、可引用。
      </LegalP>
      <LegalP>
        5. 数据诚实:行情数据来自公开行情接口,可能存在延迟或误差;我们对数据口径与局限
        如实标注,不做修饰。
      </LegalP>
      <LegalP>
        6. 隐私极简:不收集 IP、User-Agent 或任何个体行为明细,访问统计仅保留匿名聚合计数。
      </LegalP>

      <LegalH2>内容体系</LegalH2>
      <LegalP>
        训练营按六阶组织:入门筑基(K线、做多做空、杠杆、四大市场)→ 技术分析(均线、MACD、
        布林带、RSI)→ 缠论专题(分型、笔、线段、中枢、三类买卖点)→ 合约与衍生品(永续合约、
        资金费率、强平机制与合约数据)→ 策略专题(趋势跟踪、均值回归、网格等策略的原理与
        失效条件)→ 交易体系与实战(交易计划、风险与仓位、心理与复盘)。词典覆盖上述全部
        领域的核心术语,每条以「一句话定义 + 展开 + 关联词条」组织。
      </LegalP>

      <LegalH2>免责与边界</LegalH2>
      <LegalP>
        本平台提供的所有内容仅供学习、研究与参考之用,不构成、也不应被理解为任何形式的投资
        建议、财务建议、交易建议或操作指引。金融市场存在固有风险,真实投资可能导致本金的部分
        或全部损失;在做出任何真实投资决策前,请咨询具备相应资质的专业人士并独立判断。完整
        条款见风险提示、服务条款与隐私政策。
      </LegalP>
    </LegalPage>
  )
}
