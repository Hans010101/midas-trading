/**
 * 首页静态官网 · M1 第三波 任务 E。
 *
 * 设计基调:Manus 参考版的皮 + 观潮的骨架 · 9 板块从上到下:
 *   1. TopNav · 顶部导航(logo + 印章 + 锚点 + 进入终端 CTA)
 *   2. Hero · 主视觉(水墨山形 + 朱红 K 线 + 帝王金脉络)
 *   3. Showcase · 产品实拍(工作台真实截图)
 *   4. Markets · 三市场(A 股 / 美股 / 加密)
 *   5. Features · 4 张核心功能卡
 *   6. AiChan · AI + 缠论差异化展示(左右分栏 + 强制 disclaimer)
 *   7. Pricing · 定价占位(M1 限时免费 · 不写价格)
 *   8. CTA · 底部行动呼吁
 *   9. Footer · 完整页脚
 *
 * 渲染策略:Static(SSG)· 不依赖运行时数据 · 加载快。
 */

import {
  ArrowRight,
  BarChart3,
  BellRing,
  Bitcoin,
  Bot,
  CandlestickChart,
  Globe,
  ScrollText,
  Sparkles,
  Trophy,
  Wallet,
} from 'lucide-react'
import Image from 'next/image'
import Link from 'next/link'

import { cn } from '@/lib/utils'

export const dynamic = 'force-static'

export default function HomePage() {
  return (
    <main className="relative flex min-h-screen flex-col bg-background text-foreground">
      {/* 极淡纸纹背景 · 用 SVG noise · 通过 fixed 层叠在背景上 */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-0 opacity-[0.025]"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence baseFrequency='0.85' numOctaves='2'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>\")",
        }}
      />

      <TopNav />
      <Hero />
      <Showcase />
      <Markets />
      <Features />
      <AiChan />
      <Pricing />
      <BottomCTA />
      <Footer />
    </main>
  )
}


// ============================================================
// 1 · TopNav
// ============================================================


function TopNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-paper/80 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2">
          <Image
            src="/brand/seal.svg"
            alt="点金 Midas 印章"
            width={36}
            height={36}
            priority
          />
          <span className="font-serif text-xl font-bold tracking-wide">
            点金 <span className="text-midas-red">Midas</span>
          </span>
        </Link>

        <nav className="hidden items-center gap-8 text-sm md:flex">
          <a href="#showcase" className="text-muted-foreground transition-colors hover:text-foreground">
            工作台
          </a>
          <a href="#features" className="text-muted-foreground transition-colors hover:text-foreground">
            功能
          </a>
          <a href="#ai-chan" className="text-muted-foreground transition-colors hover:text-foreground">
            AI + 缠论
          </a>
          <a href="#pricing" className="text-muted-foreground transition-colors hover:text-foreground">
            定价
          </a>
        </nav>

        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="hidden text-sm text-muted-foreground transition-colors hover:text-foreground sm:inline"
          >
            登录
          </Link>
          <Link
            href="/workbench"
            className="inline-flex items-center gap-1 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-midas-red-deep"
          >
            进入终端
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </header>
  )
}


// ============================================================
// 2 · Hero
// ============================================================


function Hero() {
  return (
    <section className="relative mx-auto flex w-full max-w-7xl flex-col-reverse items-center gap-10 px-6 py-20 lg:flex-row lg:gap-16 lg:py-32">
      <div className="flex-1">
        <p className="mb-4 text-sm uppercase tracking-[0.3em] text-midas-red">
          AI 原生金融分析终端
        </p>
        <h1 className="font-serif text-5xl font-bold leading-tight tracking-tight lg:text-6xl">
          三市通览
          <span className="mx-2 text-midas-red">·</span>
          <span className="text-midas-red">点石成金</span>
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground lg:text-lg">
          覆盖 A 股、美股与加密货币三大市场,以虚拟资金零风险磨练交易直觉,让 AI 辅助你的每一次决策。
        </p>
        <div className="mt-10 flex flex-wrap items-center gap-4">
          <Link
            href="/workbench"
            className="inline-flex items-center gap-2 rounded-md bg-midas-red px-6 py-3 text-base font-medium text-white shadow-md transition-all hover:bg-midas-red-deep hover:shadow-lg"
          >
            开始分析
            <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href="#features"
            className="inline-flex items-center gap-2 rounded-md border border-midas-red bg-background px-6 py-3 text-base font-medium text-midas-red transition-colors hover:bg-midas-red-glow/40"
          >
            查看功能
          </a>
        </div>
        <div className="mt-12 flex items-center gap-6 text-xs text-muted-foreground/80">
          <Stat icon={<Trophy className="h-4 w-4 text-gold" />} label="缠论自动标注" />
          <Stat icon={<Bot className="h-4 w-4 text-midas-red" />} label="AI 决策卡" />
          <Stat icon={<Wallet className="h-4 w-4 text-gold" />} label="虚拟资金 0 风险" />
        </div>
      </div>

      <div className="relative flex flex-1 items-center justify-center">
        <div className="absolute inset-0 -z-10 rounded-full bg-gradient-to-br from-midas-red-glow/40 via-transparent to-gold/10 blur-3xl" />
        <Image
          src="/brand/hero-ink.svg"
          alt="水墨山形 + 朱红 K 线 + 帝王金脉络"
          width={600}
          height={600}
          className="h-auto w-full max-w-[520px]"
          priority
        />
      </div>
    </section>
  )
}


function Stat({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      {icon}
      <span>{label}</span>
    </div>
  )
}


// ============================================================
// 3 · Showcase(产品实拍)
// ============================================================


function Showcase() {
  return (
    <section id="showcase" className="border-y border-paper/60 bg-cream/40 py-20">
      <div className="mx-auto max-w-7xl px-6 text-center">
        <h2 className="font-serif text-3xl font-bold lg:text-4xl">
          打开即是专业终端
        </h2>
        <p className="mt-3 text-muted-foreground">
          K 线 · 缠论标注 · AI 决策卡 · 三市场切换 · 虚拟交易 · 一屏到位
        </p>
        <div className="relative mt-10">
          <div className="overflow-hidden rounded-xl border border-paper bg-background shadow-2xl">
            <Image
              src="/marketing/workbench.png"
              alt="点金 Midas 工作台:K 线 + 缠论 + AI 决策卡"
              width={1440}
              height={900}
              className="h-auto w-full"
            />
          </div>
          {/* 角标 · VIRTUAL 徽章贴在右上 */}
          <div className="absolute right-4 top-4 rounded-full border border-gold/40 bg-gold/10 px-3 py-1 font-mono text-xs text-gold">
            VIRTUAL · 模拟
          </div>
        </div>
      </div>
    </section>
  )
}


// ============================================================
// 4 · Markets(三市场)
// ============================================================


function Markets() {
  return (
    <section className="mx-auto max-w-7xl px-6 py-20">
      <div className="text-center">
        <h2 className="font-serif text-3xl font-bold lg:text-4xl">
          三市场统一体验
        </h2>
        <p className="mt-3 text-muted-foreground">
          一个终端,覆盖全球主流交易市场
        </p>
      </div>
      <div className="mt-12 grid gap-6 md:grid-cols-3">
        <MarketCard
          icon={<BarChart3 className="h-6 w-6 text-midas-red" />}
          name="A 股"
          desc="沪深全市场 · 复权口径透明"
          examples="600519 · 000001 · 300750"
        />
        <MarketCard
          icon={<Globe className="h-6 w-6 text-midas-red" />}
          name="美股"
          desc="纳斯达克 · NYSE · 后复权"
          examples="NVDA · AAPL · TSLA"
        />
        <MarketCard
          icon={<Bitcoin className="h-6 w-6 text-midas-red" />}
          name="加密"
          desc="24/7 不停盘 · Binance OHLCV"
          examples="BTC/USDT · ETH/USDT · SOL/USDT"
        />
      </div>
    </section>
  )
}


interface MarketCardProps {
  icon: React.ReactNode
  name: string
  desc: string
  examples: string
}

function MarketCard({ icon, name, desc, examples }: MarketCardProps) {
  return (
    <div className="rounded-xl border border-paper bg-cream/40 p-6 transition-all hover:border-midas-red hover:shadow-md">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-midas-red-glow/40">
        {icon}
      </div>
      <h3 className="font-serif text-xl font-bold">{name}</h3>
      <p className="mt-2 text-sm text-muted-foreground">{desc}</p>
      <p className="mt-3 font-mono text-xs text-muted-foreground/70">
        {examples}
      </p>
    </div>
  )
}


// ============================================================
// 5 · Features(核心功能)
// ============================================================


function Features() {
  return (
    <section
      id="features"
      className="border-y border-paper/60 bg-cream/40 py-20"
    >
      <div className="mx-auto max-w-7xl px-6">
        <div className="text-center">
          <h2 className="font-serif text-3xl font-bold lg:text-4xl">核心功能</h2>
          <p className="mt-3 text-muted-foreground">
            为认真对待投资的你而设计
          </p>
        </div>
        <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          <FeatureCard
            icon={<CandlestickChart className="h-6 w-6 text-midas-red" />}
            title="K 线工作台"
            desc="MA / MACD / RSI / BOLL 指标 + 多周期(1m → 1w) + 三市场标的搜索"
          />
          <FeatureCard
            icon={<Wallet className="h-6 w-6 text-midas-red" />}
            title="虚拟交易"
            desc="三市场独立钱包 · CNY / USD / USDT 原币结算 · 永远不接真实交易"
          />
          <FeatureCard
            icon={<BellRing className="h-6 w-6 text-midas-red" />}
            title="智能推送"
            desc="飞书 / Telegram / 邮件 · 价格异动 + 成交提醒 + 自定义阈值"
          />
          <FeatureCard
            icon={<Sparkles className="h-6 w-6 text-midas-red" />}
            title="AI 决策卡"
            desc="LangGraph + DeepSeek 多维研判 · 自动生成结构化分析与关键位"
          />
        </div>
      </div>
    </section>
  )
}


interface FeatureCardProps {
  icon: React.ReactNode
  title: string
  desc: string
}

function FeatureCard({ icon, title, desc }: FeatureCardProps) {
  return (
    <div className="rounded-xl border border-paper bg-background p-6 transition-all hover:border-midas-red hover:shadow-md">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-midas-red-glow/40">
        {icon}
      </div>
      <h3 className="font-serif text-lg font-bold">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{desc}</p>
    </div>
  )
}


// ============================================================
// 6 · AiChan(AI + 缠论差异化)· 重点板块
// ============================================================


function AiChan() {
  return (
    <section id="ai-chan" className="mx-auto max-w-7xl px-6 py-24">
      <div className="text-center">
        <p className="mb-3 text-sm uppercase tracking-[0.3em] text-gold">
          差异化能力
        </p>
        <h2 className="font-serif text-3xl font-bold lg:text-4xl">
          不只是看图,更懂走势
        </h2>
        <p className="mt-3 text-muted-foreground">
          czsc 缠论自动标注 + DeepSeek AI 多维研判 · 数据 + 模型双驱动
        </p>
      </div>

      <div className="mt-14 grid gap-10 lg:grid-cols-2">
        {/* 左侧 · 缠论自动标注 */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <ScrollText className="h-5 w-5 text-gold" />
            <h3 className="font-serif text-xl font-bold">缠论自动标注</h3>
          </div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            基于 czsc 库识别:笔(帝王金连线)· 顶分型(墨绿▽)· 底分型(朱红△)· 中枢(淡灰蓝矩形)· 一/二/三类买卖点。
            画在你熟悉的 K 线上,不打扰主图阅读。
          </p>
          <div className="overflow-hidden rounded-xl border border-paper bg-background shadow-lg">
            <Image
              src="/marketing/chan.png"
              alt="缠论自动标注 · 笔/分型/中枢"
              width={1440}
              height={900}
              className="h-auto w-full"
            />
          </div>
        </div>

        {/* 右侧 · AI 决策卡 */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-midas-red" />
            <h3 className="font-serif text-xl font-bold">AI 决策卡</h3>
          </div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            LangGraph workflow 把 K 线 + 缠论结构 + 4 项指标喂给 DeepSeek · 输出结构化评分(强多/弱多/中性/弱空/强空)+ 关键支撑阻力位 + 中文解读。
            缓存命中 35× 提速,百用户月费仅 ¥1.7。
          </p>
          <div className="overflow-hidden rounded-xl border border-paper bg-background shadow-lg">
            <Image
              src="/marketing/ai-card.png"
              alt="AI 决策卡 · 综合评分 + 缠论买卖点"
              width={600}
              height={900}
              className="h-auto w-full"
            />
          </div>
        </div>
      </div>

      {/* 强制 disclaimer · 跟 0011 / 0012 ADR 红线一致 */}
      <div className="mx-auto mt-10 max-w-3xl rounded-lg border border-paper bg-cream/60 px-5 py-3 text-center">
        <p className="font-mono text-xs text-muted-foreground/80">
          ⚠ 分析仅供参考,不构成投资建议。所有交易均为虚拟资金模拟。
        </p>
      </div>
    </section>
  )
}


// ============================================================
// 7 · Pricing(M1 占位 · 不写死价格)
// ============================================================


function Pricing() {
  return (
    <section
      id="pricing"
      className="border-y border-paper/60 bg-cream/40 py-20"
    >
      <div className="mx-auto max-w-3xl px-6 text-center">
        <h2 className="font-serif text-3xl font-bold lg:text-4xl">定价</h2>
        <div className="mt-10 rounded-2xl border-2 border-gold/40 bg-background p-10 shadow-md">
          <div className="mb-4 inline-block rounded-full border border-gold bg-gold/10 px-4 py-1.5 font-mono text-xs text-gold">
            限时免费 · 内测中
          </div>
          <h3 className="mt-2 font-serif text-2xl font-bold">
            点金 Midas 正在内测
          </h3>
          <p className="mt-4 text-base leading-relaxed text-muted-foreground">
            当前所有功能免费开放。会员方案规划中,敬请期待。
          </p>
          <Link
            href="/workbench"
            className="mt-8 inline-flex items-center gap-2 rounded-md bg-midas-red px-6 py-3 text-base font-medium text-white shadow-sm transition-colors hover:bg-midas-red-deep"
          >
            立即体验
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </section>
  )
}


// ============================================================
// 8 · BottomCTA
// ============================================================


function BottomCTA() {
  return (
    <section className="mx-auto max-w-7xl px-6 py-24 text-center">
      <h2 className="font-serif text-3xl font-bold lg:text-4xl">
        开始你的第一笔虚拟交易
      </h2>
      <p className="mt-4 text-muted-foreground">
        0 风险 · 0 成本 · 不需要真金白银,只磨练你的判断
      </p>
      <div className="mt-8">
        <Link
          href="/workbench"
          className="inline-flex items-center gap-2 rounded-md bg-midas-red px-8 py-4 text-lg font-medium text-white shadow-lg transition-all hover:bg-midas-red-deep hover:shadow-xl"
        >
          进入终端
          <ArrowRight className="h-5 w-5" />
        </Link>
      </div>
    </section>
  )
}


// ============================================================
// 9 · Footer
// ============================================================


function Footer() {
  return (
    <footer className="border-t border-paper bg-cream/60">
      <div className="mx-auto max-w-7xl px-6 py-12">
        <div className="grid gap-10 md:grid-cols-4">
          <div className="md:col-span-2">
            <div className="flex items-center gap-2">
              <Image
                src="/brand/seal.svg"
                alt="点金 Midas 印章"
                width={32}
                height={32}
              />
              <span className="font-serif text-lg font-bold">
                点金 <span className="text-midas-red">Midas</span>
              </span>
            </div>
            <p className="mt-3 max-w-md text-sm text-muted-foreground">
              点金 Midas · 仅供模拟交易,不构成投资建议。所有数据来自公开行情接口,AI 分析输出仅作参考。
            </p>
          </div>
          <FooterCol
            title="产品"
            links={[
              { label: '工作台', href: '/workbench' },
              { label: '功能', href: '#features' },
              { label: 'AI + 缠论', href: '#ai-chan' },
              { label: '定价', href: '#pricing' },
            ]}
          />
          <FooterCol
            title="法务"
            links={[
              // M2 填实际内容 · 先放占位锚点
              { label: '服务条款', href: '#' },
              { label: '隐私政策', href: '#' },
              { label: '风险提示', href: '#' },
              { label: '联系我们', href: '#' },
            ]}
          />
        </div>
        <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-paper pt-6 text-xs text-muted-foreground md:flex-row">
          <p>© 2026 点金 Midas. All rights reserved.</p>
          <p className="font-mono">仅供模拟交易,不构成投资建议</p>
        </div>
      </div>
    </footer>
  )
}


interface FooterColProps {
  title: string
  links: { label: string; href: string }[]
}

function FooterCol({ title, links }: FooterColProps) {
  return (
    <div>
      <h4 className="mb-3 font-serif text-sm font-bold text-foreground">{title}</h4>
      <ul className="space-y-2 text-sm">
        {links.map((l) => (
          <li key={l.label}>
            <Link
              href={l.href as never}
              className={cn(
                'text-muted-foreground transition-colors hover:text-midas-red',
              )}
            >
              {l.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
