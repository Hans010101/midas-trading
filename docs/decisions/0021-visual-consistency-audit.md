# 0021 · 全产品视觉一致性盘点(为统一设计规范做准备)

## 状态

**诊断报告 · 只读盘点**(2026-05-24)。本文档**只盘点、不改任何代码、不 push**。
产出供下一步「建统一设计规范(Design Tokens)+ A股/美股首页改版」决策使用。

> 本盘点为只读审计:所列 className / 色值均摘自现有源码,未做任何修改。

## 背景

产品分阶段迭代而成,不同时期写的:加密频道(M2-A/B/D)、合约虚拟交易(M2-C)、
早期 0008 现货虚拟交易、A股/美股工作台、我的账户、全站导航。需要全面盘一遍视觉
一致性,为接下来建统一设计规范做准备。

## 盘点范围(界面 → 关键文件)

| 界面 | 关键文件 |
|---|---|
| 全站导航 | `components/layout/top-nav.tsx` |
| 市场切换条 | `components/layout/market-switcher.tsx` |
| 加密市场列表页 `/crypto-market` | `app/crypto-market/page.tsx` |
| 加密详情页 `/crypto-preview` | `crypto-detail / crypto-header / crypto-main-chart / dimension-section / crypto-ai-card / perp-order-guidance / strategy-checklist / crypto-perp-orders` |
| A股/美股工作台 `/workbench` | `workbench/{header,page,current-position-card,order-confirm-dialog,symbol-switcher,signal-bar,watchlist-column,chart-area,kline-context-menu}` |
| 0008 现货下单/持仓 | `workbench/order-confirm-dialog` · `workbench/current-position-card` · `workbench/header`(买卖按钮) |
| 我的账户 `/account` | `app/account/page.tsx` · `account/wallet-section.tsx` · `account/perp-positions-section.tsx` |
| 设计底座 | `tailwind.config.ts` · `app/globals.css` · `components/ui/*` |

---

## §0 根因:两套设计基准并存

产品有一套**完整但基本闲置**的 shadcn 组件库 + token,真实界面却几乎全部**手搓**
`<div>`/`<button>`/`<table>`:

- `components/ui/`:`Button` `Card` `Input` `Badge` `Tabs` `Dialog` `Tooltip` `Sonner` `command` `context-menu` `dropdown-menu` —— 其中 **Button / Input / Tabs / Badge / Card 几乎零业务使用**;实际在用的只有 Sonner(toast)、Tooltip、command(搜索)、context-menu 思路、Dialog 思路(多数弹窗也手搓)。
- `VirtualBadge` 是**唯一被广泛复用**的自定义组件(但 `/account` 又手搓了一个重复版,见 §1.7)。

### 🔴 最关键根因:主红有三套并存

| 名称 | 定义 | 谁在用 |
|---|---|---|
| `midas-red` | `#C8102E`(hex,tailwind.config) | **所有手搓组件**(按钮/边框/active) |
| `primary` | HSL `350 88% 43%` ≈ `#CE0E33`(globals.css) | shadcn `Button` default、`Badge` default、`market-switcher` 的 `text-primary-foreground` |
| `destructive` | HSL `0 84% 60%`(globals.css) | shadcn `Button`/`Badge` destructive 变体——**实际无人用** |

`midas-red(#C8102E)` 与 `primary(≈#CE0E33)` **接近但不等值**,只要混用 shadcn 组件就会出现
肉眼可辨的红色偏差;`destructive` 更是一个完全不同的非品牌红。**这是统一的第一优先项。**

---

## §1 逐维度不一致清单

> ✅ = 已一致(不用动)· ❌ = 不一致 · ⚠️ = 缺失/隐患

### 1.1 颜色

- ✅ **涨跌语义全站一致**:`text-bull`(`#DC143C` 朱红=涨)/ `text-bear`(`#0F6E5F` 墨绿=跌),A股「红涨绿跌」贯穿所有市场(含加密)。
  - ⚠️ **产品决策点**:加密频道也用了 A股红涨绿跌,与加密西方惯例(绿涨红跌)相反。内部一致,但需产品方确认是否有意为之。
- ❌ **主红三套并存**(见 §0)。`market-switcher` active 用 `text-primary-foreground`,其余主按钮用字面 `text-white`。
- ❌ **外层边框色不一**:`top-nav` 用 `border-paper`;`workbench/header` 与 `watchlist-column` 用 `border-midas-red`;`crypto-header` 用 `border-paper`。
- ❌ **卡片背景透明度随意**:`bg-cream`(workbench / account / 列表 MetricCard)· `bg-cream/30`(合约维度图)· `bg-cream/40`(策略清单 / 本币订单 / crypto-header)· `bg-gold/5`(下单指导)。
- ⚠️ **状态色无统一色板**:`text-warn`(`#B45309`,在 tailwind.config 但 globals.css 无对应 HSL、README 视觉系统未列)用于「未设置」「context-menu 警告」;预警混用 `midas-red` / `bear`;无统一「警告 / 成功 / 危险 / 信息」语义色。

### 1.2 按钮

- ❌ **零 shadcn `<Button>` 使用**,全手搓。主按钮大体统一为 `bg-midas-red text-white hover:bg-midas-red-deep`,但:
  - **padding 乱**:`px-4 py-1.5`(header 买入)· `px-3 py-1.5`(持仓卡平仓)· `px-4 py-2`(wallet 激活 / watchlist 空态 CTA)· `px-2 py-1`(account/perp 平仓)。
  - **radius 乱**:多数 `rounded-md`(6px),但 `/account` 平仓、perp 平仓用 `rounded`(4px)。
  - **disabled 乱**:手搓用 `bg-midas-red/30`,shadcn 用 `opacity-50`。
- 次按钮(outline)大体统一 `border border-midas-red text-midas-red hover:bg-midas-red-glow`,但 hover 透明度档(`/40` 时有时无)不一。
- ❌ **无独立「危险」按钮样式**:平仓 / 重置都复用主红或 outline-red;shadcn `destructive`(那套非品牌红)无人用。

### 1.3 卡片 / 容器

- ❌ **radius**:卡片多数 `rounded-lg`(8px),但 `current-position-card` 与 `kline-context-menu` 用 `rounded-md`(6px);pill 用 `rounded`(4px)或 `rounded-full`。
- ❌ **padding 无节奏**:`p-3`(合约维度图 / 本币订单)· `p-4`(列表 MetricCard / 策略 / 下单指导)· `p-5`(account / wallet KPICard)· `p-6`(shadcn Card 默认 / 部分弹窗)。
- ❌ **border 风格**:`border border-paper`(绝大多数)· `border-2 border-gold`(持仓卡)· `border-dashed border-gold/60`(下单指导)。
- ❌ **shadow**:`shadow-sm`(多数)· `shadow-xl`(弹窗 / 菜单)· 无(合约维度图卡)。
- shadcn `Card` 默认 `rounded-lg border bg-card shadow-sm` + `p-6`——与手搓卡(`bg-cream` / `p-3~p-5`)不一致,故无人用。

### 1.4 字体

- ✅ 标题统一 `font-serif … font-bold`;数字统一 `font-mono`。
- ❌ **字号梯度乱**:H1 `text-2xl`;Section `text-xl` 与 `text-lg`(account 内部混用);卡片标题 `text-base` / `text-sm`;正文 `text-sm` / `text-xs` / `text-[10px]` / `text-[11px]` 无统一 scale。
- ❌ **tabular-nums 时有时无**:`watchlist` / `signal-bar` 用 `tabular-nums`,多数 perp 表不用;`globals.css` 的 `.font-tabular` 工具类几乎没人用。

### 1.5 间距

- ❌ **section 间距**:`mb-10`(account section)· `mb-6` · `space-y-4`(crypto 右栏)。
- ❌ **页面容器无统一 shell**:`/account` 用 `max-w-6xl px-6 py-8`;`/crypto-preview` 用 `max-w-[1600px] px-4 py-4`;`/crypto-market` 另一套。
- ❌ 元素 `gap-1 / 1.5 / 2 / 3 / 4` 混用。

### 1.6 表格

- ❌ **两种风格并存**:
  - **列表页**(`crypto-market`):`overflow-x-auto rounded-lg border border-paper` wrapper · thead `bg-cream/50` · cell `px-3 py-2.5` · 行 hover `bg-midas-red-glow/30`。
  - **account / perp 表**:**无 wrapper / 无 border** · thead 无背景色 · cell `py-2`(无横向 padding);`crypto-perp-orders` 更用 thead `text-[10px]` + cell `py-1.5`。
- ✅ 一致项:均无斑马纹;数字列均右对齐。

### 1.7 徽章 / 标签

- ❌ **VirtualBadge 被重复实现**:组件版 = `rounded-full bg-gold/[0.08] border-gold/40 text-gold`;但 `/account` 手搓了一个 `rounded`(非 full)`bg-gold/[0.08] border-gold`(border 不带 `/40`)的「VIRTUAL · 模拟」——形状 + border 都不同。
- ❌ **方向 pill 各处手搓**:买/卖(order-dialog、account)、多/空(perp `SideBadge` 带杠杆、本币订单)四套近似但非共用组件,样式 `rounded px-1.5 py-0.5` + `bg-midas-red` / `border-midas-red` 或 `bg-bull` / `bg-bear`。
- ❌ 市场 chip(`watchlist` 的 cn/us/crypto 三色)又是独立一套;shadcn `<Badge>` 无人用。

### 1.8 表单 / 滑块 / Tab / 空态 / loading / toast

- ❌ **输入框**:有 shadcn `<Input>`(`h-10 rounded-md border-input`),但 `order-dialog`(`h-8 rounded border-paper`)、`wallet`(`h-10 rounded-md border-paper`)、crypto 保证金输入全手搓——**几乎没人用 `<Input>`**。
- ❌ **Tab**:有 shadcn `<Tabs>`,但 `market-switcher` / `crypto-market` / `crypto-header` / 周期切换全手搓,active 风格两套(`bg-midas-red text-white` vs `bg-midas-red-glow text-midas-red`)。
- 滑块:`perp-order-guidance` 杠杆用原生 `range` + `accent-midas-red`(单点,暂无一致性问题)。
- ❌ **空态 / loading 文案不统一**:「载入中…」「加载中…」「分析中...」并存;空态样式 `text-xs` / `text-sm` + `text-muted-foreground/60`,有的带图标卡(watchlist)有的纯文字。
- ✅ **toast 一致**:全站 sonner,success 用 `midas-toast-success`,duration 4000/5000。

---

## §2 现有可作统一基准的资产

- **token 底座**(`tailwind.config.ts`):品牌色 `midas-red / gold / bull / bear / paper / cream / ink / warn` + shadcn HSL token + radius scale(`2/4/6/8`)+ fontFamily(`serif / sans / mono`)。**够用,只差「语义层」与「组件 recipe」。**
- **shadcn 组件库**:存在即可改造,不必从零。
- **已经一致、不用动的**:涨跌 `bull/bear` 语义、数字 `font-mono`、标题 `font-serif`、toast(sonner)、空值哨兵 `—`、无斑马纹 + 数字右对齐。

---

## §3 工作量 / 范围 / 风险

**范围**:约 25–30 个组件/页面文件。按风险分三档:

| 档 | 内容 | 风险 |
|---|---|---|
| **零风险**(纯换 class,不动布局) | 三套红收口为单一 action-primary;`bg-cream` 透明度定 1–2 档;卡片 radius/shadow 统一;空态/loading 文案统一;`tabular-nums` 补齐;`/account` 手搓 VirtualBadge → 换组件 | 极低 |
| **中风险**(可能微调行高/列宽/排布) | 表格统一(wrapper + cell padding 改行高列宽)· 按钮 padding/radius 统一(影响 header 工具条紧凑排布)· 字号 scale 收敛 | 中 · 需逐页回看 |
| **高风险**(改 DOM / 结构) | 手搓组件迁移到 shadcn `Button`/`Input`/`Tabs`/`Badge`(改结构 + 事件/样式继承,**workbench header 工具条最敏感**)· 加密涨跌色若改西方惯例(产品决策) | 高 · 谨慎、分批 |

---

## §4 建议

### 4.1 Design Tokens 三层组织

1. **原始色板**(已有 hex,不动)。
2. **语义 token**(新增,最高优先):
   - 动作:`action-primary` / `action-secondary` / `action-danger`(先把三套红收口为 `action-primary`)
   - 表面:`surface-page` / `surface-card` / `surface-raised`(把 `cream` 透明度定档)
   - 边框:`border-default` / `border-strong`
   - 文字:`text-primary` / `text-muted` / `text-faint`
   - 行情:`up` / `down`(= bull/bear)
   - 状态:`state-warn` / `state-success` / `state-info`
3. **组件 recipe**(把高频手搓模式封成共用组件或 cva variant):`Button`(主/次/危险 × sm/md)、`Card`(标准 radius/padding/shadow/bg)、`DataTable`(thead/cell/hover 标准)、`StatusPill` / `DirectionBadge`、`EmptyState` / `LoadingNote`。

### 4.2 落地顺序

1. 先做**零风险换色 + 卡片/空态标准化**(独立小 PR,先把「看起来乱」消掉)。
2. 再封 ~5 个共用组件;**A股/美股首页改版直接用新规范打样**,验证后回头替换存量。
3. 中/高风险项分批替换,`workbench/header` 工具条单独处理、单独回归。

### 4.3 需产品方拍板的点

- 加密频道涨跌色是否沿用 A股「红涨绿跌」(当前如此,与加密西方惯例相反)。
- 主红最终基准取 `#C8102E`(midas-red)还是 HSL primary(二者接近,需定一个为唯一真源)。

---

## 附:盘点方法

- 全程只读源码(`tailwind.config.ts` / `globals.css` / `components/ui/*` / 各界面组件),逐文件提取
  实际 className / 色值 / radius / padding,跨界面对照。
- 未运行修改、未提交、未 push。
