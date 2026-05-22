/**
 * M2-D · 加密币种详情页 · 静态布局骨架(预览用)
 *
 * ⚠ 这是【布局骨架】· 不是功能页面:
 *   · 所有图表 = 占位框(示意框 + 标题)· 不接真实数据 · 不调后端 API
 *   · 所有数值 = 示意值
 *   · 目的:让产品方先看清"页面长什么样、各模块怎么排版、比例"
 *
 * 来源:commit 9594f93 登记的 M2-D 需求。
 * 红线:点金永远只用虚拟资金 · 绝不接真实交易通道 · "下单指导"语义全程虚拟。
 *
 * 预览:本地 pnpm dev → http://localhost:3000/crypto-preview
 *
 * 后续真实接入(不在本步):
 *   · 主图 + 6 维度图 → M2-B 后端 REST(/api/v1/crypto/*)
 *   · 多空人数比 / 基差 → M2-B 待补 2 个数据缺口
 *   · AI 决策卡吃合约数据 → M2-B/M2-C workflow
 *   · 下单指导 / 实战策略 → 虚拟交易模块(M2-C)
 */

export const dynamic = 'force-static'

export default function CryptoPreviewPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      {/* ── 顶部:预览横幅(明确这是骨架)── */}
      <div className="border-b border-dashed border-gold/60 bg-gold/10 px-6 py-2 text-center text-xs text-gold">
        M2-D 布局骨架预览 · 所有图表为占位框 · 数值为示意 · 不接真实数据
      </div>

      <Header />

      {/* ── 主体:左主区 + 右侧栏 ── */}
      <div className="mx-auto flex max-w-[1600px] gap-4 px-4 py-4">
        {/* 左主区 ~70% */}
        <div className="flex-1 space-y-4">
          {/* 1 · 主图:K线 + 缠论 */}
          <PlaceholderChart
            title="主图:K 线 + 缠论标注"
            sub="蜡烛图 + 笔(金)/ 顶底分型 / 中枢(淡灰蓝)· 现货/合约 K 线可切"
            heightClass="h-[420px]"
          />

          {/* 2 · 6 个合约维度图 · 2 列 × 3 行 */}
          <div>
            <h3 className="mb-2 font-serif text-base font-bold">合约维度</h3>
            <div className="grid grid-cols-2 gap-4">
              <PlaceholderChart title="① 合约持仓量(OI)" sub="oi_usd / oi_coin · 5min" heightClass="h-44" />
              <PlaceholderChart title="② 大户多空比 · 账户数" sub="topLongShortAccountRatio · 5min" heightClass="h-44" />
              <PlaceholderChart title="③ 大户多空比 · 持仓量" sub="topLongShortPositionRatio · 5min" heightClass="h-44" />
              <PlaceholderChart title="④ 多空人数比值" sub="globalLongShortAccountRatio · M2-B 待补采集" heightClass="h-44" pending />
              <PlaceholderChart title="⑤ 合约主动买卖量" sub="taker buy/sell · 5min" heightClass="h-44" />
              <PlaceholderChart title="⑥ 基差(basis)" sub="mark − index · M2-B 待补采集" heightClass="h-44" pending />
            </div>
          </div>
        </div>

        {/* 右侧栏 ~固定 360px */}
        <aside className="w-[360px] shrink-0 space-y-4">
          <AiDecisionCard />
          <OrderGuidance />
          <StrategyChecklist />
        </aside>
      </div>
    </main>
  )
}

// ============================================================
// 顶部 Header · symbol + 现货/合约 tab + 周期 + 虚拟徽章
// ============================================================
function Header() {
  return (
    <header className="border-b border-paper bg-cream/40 px-6 py-3">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex items-baseline gap-2">
          <span className="font-serif text-2xl font-bold">BTC/USDT</span>
          <span className="font-mono text-lg font-bold text-bull">$64,820.5</span>
          <span className="font-mono text-sm text-bull">+2.34%</span>
        </div>

        <VirtualBadge />

        {/* 现货 / 合约 tab(占位)*/}
        <div className="flex overflow-hidden rounded-md border border-paper text-sm">
          <span className="bg-midas-red px-3 py-1 text-white">合约</span>
          <span className="px-3 py-1 text-muted-foreground">现货</span>
        </div>

        {/* 周期切换(占位)*/}
        <div className="flex gap-1 text-xs">
          {['15m', '1h', '4h', '1d'].map((p) => (
            <span
              key={p}
              className={`rounded px-2 py-1 ${p === '1h' ? 'bg-midas-red-glow text-midas-red' : 'text-muted-foreground'}`}
            >
              {p}
            </span>
          ))}
        </div>

        <div className="ml-auto font-mono text-xs text-muted-foreground">
          下次资金费率 03:21:08 · 费率 +0.0100%(示意)
        </div>
      </div>
    </header>
  )
}

// ============================================================
// 占位图表框
// ============================================================
function PlaceholderChart({
  title,
  sub,
  heightClass,
  pending = false,
}: {
  title: string
  sub?: string
  heightClass: string
  pending?: boolean
}) {
  return (
    <div className="rounded-lg border border-paper bg-cream/30 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-serif text-sm font-bold">{title}</span>
        {pending && (
          <span className="rounded bg-gold/15 px-1.5 py-0.5 text-[10px] text-gold">
            数据 M2-B 待补
          </span>
        )}
      </div>
      <div
        className={`flex ${heightClass} items-center justify-center rounded-md border border-dashed border-paper bg-background/60`}
      >
        <div className="text-center">
          <div className="font-mono text-xs text-muted-foreground/60">[ 图表占位 ]</div>
          {sub && <div className="mt-1 text-[11px] text-muted-foreground/50">{sub}</div>}
        </div>
      </div>
    </div>
  )
}

// ============================================================
// 右栏 1 · AI 决策卡(多空研判已并入 · 合并一张 · 非两张并列)
// ============================================================
function AiDecisionCard() {
  return (
    <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-serif text-base font-bold text-midas-red">AI 决策卡</span>
        <span className="rounded bg-midas-red-glow px-2 py-0.5 text-[10px] text-midas-red">
          技术面 + 合约面 · 合并版
        </span>
      </div>

      {/* 综合评分(示意)*/}
      <div className="mb-3 flex items-end gap-2">
        <span className="font-mono text-3xl font-bold text-bull">72</span>
        <span className="mb-1 text-sm text-bull">偏多 · 示意</span>
      </div>

      {/* 多空研判(并入本卡的子段 · 不另起一张)*/}
      <div className="mb-3 rounded-md bg-background/60 p-2">
        <div className="mb-1 text-xs font-medium text-muted-foreground">多空研判(合约面)</div>
        <ul className="space-y-1 text-xs text-foreground/80">
          <li>· 大户持仓多空比 1.85 偏多(示意)</li>
          <li>· 资金费率 +0.01% · 多头付费(示意)</li>
          <li>· OI 24h +8.2% · 增仓上行(示意)</li>
        </ul>
      </div>

      {/* 技术面 / 缠论(示意)*/}
      <div className="mb-3 text-xs text-foreground/80">
        <div className="mb-1 font-medium text-muted-foreground">技术面 · 缠论</div>
        <p>1h 级别中枢上移 · 近期一买信号 · 关注 63,200 支撑(示意)。</p>
      </div>

      <p className="border-t border-paper pt-2 text-[10px] text-muted-foreground/70">
        仅供参考,不构成投资建议 · 虚拟模拟
      </p>
    </div>
  )
}

// ============================================================
// 右栏 2 · 下单指导(占位 · 待虚拟交易模块接入)· 全程虚拟资金
// ============================================================
function OrderGuidance() {
  return (
    <div className="rounded-lg border border-dashed border-gold/60 bg-gold/5 p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-serif text-base font-bold">下单指导</span>
        <VirtualBadge />
      </div>
      <p className="mb-3 rounded bg-gold/15 px-2 py-1 text-[11px] text-gold">
        【占位 · 待虚拟交易模块接入(M2-C)】
      </p>

      {/* 虚拟下单示意控件(纯静态)*/}
      <div className="space-y-2 text-sm opacity-60">
        <div className="flex gap-2">
          <span className="flex-1 rounded bg-bull/15 py-1.5 text-center text-bull">开多(虚拟)</span>
          <span className="flex-1 rounded bg-bear/15 py-1.5 text-center text-bear">开空(虚拟)</span>
        </div>
        <div className="flex items-center justify-between rounded border border-paper px-2 py-1.5 text-xs text-muted-foreground">
          <span>杠杆</span><span className="font-mono">10x(示意)</span>
        </div>
        <div className="flex items-center justify-between rounded border border-paper px-2 py-1.5 text-xs text-muted-foreground">
          <span>保证金(虚拟 USDT)</span><span className="font-mono">500.00</span>
        </div>
        <div className="flex items-center justify-between rounded border border-paper px-2 py-1.5 text-xs text-muted-foreground">
          <span>预估强平价</span><span className="font-mono">58,410.0</span>
        </div>
      </div>
      <p className="mt-3 text-[10px] text-muted-foreground/70">
        全程虚拟资金 · 绝不接真实交易所下单 · 所有动作走点金虚拟撮合(M2-C)
      </p>
    </div>
  )
}

// ============================================================
// 右栏 3 · 实战策略清单(占位 · 待虚拟交易模块接入)
// ============================================================
function StrategyChecklist() {
  return (
    <div className="rounded-lg border border-dashed border-gold/60 bg-gold/5 p-4">
      <div className="mb-2 font-serif text-base font-bold">实战策略清单</div>
      <p className="mb-3 rounded bg-gold/15 px-2 py-1 text-[11px] text-gold">
        【占位 · 待虚拟交易模块接入(M2-C)】
      </p>
      <ul className="space-y-2 text-xs text-foreground/70 opacity-60">
        <li className="flex gap-2"><span className="text-gold">▢</span> 资金费率为正且 OI 增 → 顺势虚拟开多(示意)</li>
        <li className="flex gap-2"><span className="text-gold">▢</span> 大户多空比极端 → 反向预警(示意)</li>
        <li className="flex gap-2"><span className="text-gold">▢</span> 缠论一卖 + 基差走弱 → 虚拟减仓(示意)</li>
        <li className="flex gap-2"><span className="text-gold">▢</span> 强平价距现价 &lt; 5% → 降杠杆提示(示意)</li>
      </ul>
      <p className="mt-3 text-[10px] text-muted-foreground/70">
        策略仅供参考,不构成投资建议 · 全程虚拟
      </p>
    </div>
  )
}

// ============================================================
// 帝王金 VIRTUAL 徽章(CLAUDE.md 视觉系统:虚拟交易元素必带)
// ============================================================
function VirtualBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-gold/50 bg-gold/10 px-2 py-0.5 text-[10px] font-medium tracking-wide text-gold">
      VIRTUAL · 模拟
    </span>
  )
}
