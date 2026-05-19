# KLineChart 选型决策 · 0004

## 状态
Approved (2026-05-19)

## 决策
**走 `klinecharts` 基础库(免费,Apache-2.0),自写 React 19 薄 wrapper。**

**不用** `@klinecharts/pro`(尽管同样免费 Apache-2.0,但栈不匹配 + 维护停滞)。

## 调研事实(2026-05-19,权威来源)

### `klinecharts`(base · 主选)
| 项 | 数据 | 来源 |
|---|---|---|
| License | **Apache-2.0** | `gh api repos/klinecharts/KLineChart` |
| 最新版本 | **10.0.0-beta1**(108 个 release) | `npm view klinecharts` |
| 最后一次 push | **2026-05-18**(本调研前一天) | `gh api` |
| Stars | **3,783** | `gh api` |
| 依赖 | **0**(纯 canvas + 原生 TS,无 framework dep) | `npm view` |
| 体积 | ~40 KB gzipped | 官网首页 |
| M0 4 指标支持 | **MA / MACD / RSI / BOLL 内置**,官网首页明确点名 | klinecharts.com/en-US/ |
| Overlay / 缠论标注 API | "Rich APIs ... line drawing models, overlays" | 同上 |
| 周期切换 | 库本身不限,timeframe 由调用方控制 | 同上 |
| 移动端支持 | 是 | repo description |

### `@klinecharts/pro`(被淘汰)
| 项 | 数据 |
|---|---|
| License | **Apache-2.0**(同样开源,**不是付费版**)|
| 最新版本 | **0.1.1**,只有 2 个 release |
| 最后一次 push | **2024-07-03**(~2 年没更新)|
| Stars | 295 |
| 开放 issues | 55 |
| 底层 framework | **solid-js**(不是 React)|
| 依赖 | `lodash` + `solid-js` |
| 描述 | "Financial chart built out of the box based on KLineChart" |

## 理由(5 条)

1. **栈不匹配 · 决定性因素。** 本项目锁死 Next 15 + React 19。`@klinecharts/pro` 用 solid-js,要嵌入需走 web component 或 framework bridge,引入 framework 双栈 + 包大小 + 范式割裂,不值得。
2. **base 主动维护 · pro 停滞。** base 昨天(2026-05-18)还在更新到 10.0.0-beta1;pro 停在 0.1.1 已经将近 2 年。3.7k stars vs 295 stars 也说明社区共识。
3. **M0 + M1 需要的能力 base 全有。** 官网首页明确列出 MA/MACD/RSI/BOLL 内置,overlay API + line drawing 用于 M1 缠论标注无障碍。
4. **Apache-2.0 兼容 SaaS 商业使用。** 允许我们这种付费/订阅托管。无 GPL 传染性,无 attribution 强制要求(只需保留 LICENSE 文本)。
5. **零依赖意味着可控。** 4 个 base 适配 wrapper 写起来 ~100 行 React 代码,future-proof。

## 三原则匹配

| 原则 | 判断 |
|---|---|
| 免费版能满足 M0 + M1 → 免费 | ✅ **满足** |
| 付费版便宜 + 跨越式更好 → 付费 | ❌(没有付费版,pro 不算)|
| 付费版贵或 license 不兼容 → 免费自研 | N/A(因为没有付费版)|

**结论:** 走 base,理由 = 第 1 条命中(免费够用)+ 栈匹配(决定性)。

## 影响范围

### Task 3 G Checkpoint
- `pnpm add klinecharts@^10.0.0-beta1`(注意 beta 标签,稳定后切 ^10.0.0)
- 自写 `apps/web/components/chart/KlineChart.tsx`(~100 行):
  - 接 `klinecharts.init(container)` → 拿到 chart 实例
  - 用 `useEffect` 管理生命周期(componentDidMount → unmount destroy)
  - 接受 props `symbol / market / period / indicators?`,内部调 `/api/v1/market/kline` 拉数据
  - 暴露 ref API 给后续 M1 用 `chart.createOverlay(...)`
- 主色 / 涨跌 / 字体 全部走 04 文档的视觉 token

### Task 3 H Checkpoint
- 周期切换器 + 4 指标 toggle 用 klinecharts 内置 API
- 标的搜索切换 → 重新调 `useKline(symbol)`,KLineChart 实例复用

### M1 缠论标注
- klinecharts 的 Overlay API 兼容,缠论笔/段/枢纽用 overlay 画即可
- 不需要切换图表库

## 撤销路径

- **若 base klinecharts 不够用(罕见):** 候选评估
  1. **TradingView lightweight-charts**(Apache-2.0,GitHub 9k+ stars,React 友好)
  2. **echarts-financial**(Apache-2.0,Baidu 出品,生态成熟)
  3. **AntV G2 / G6**(MIT,蚂蚁出品)
- 切换成本:KlineChart wrapper 接口稳定,只换内部实现 ~1 天
- **付费方向不考虑:** TradingView Charting Library 有商业 license 限制,不适合 SaaS。Highcharts 也是。

## 备注

- 04 文档原写 `@klinecharts/pro` —— Manus 当时没仔细看,这是个**命名误导**(Pro 听起来像付费,实际是 solid-js 开箱即用 starter)。改用 base 不破坏 04 的视觉/技术意图。
- `klinecharts@10.0.0-beta1` 是 beta 标签,**正式版可能在 Task 3 开干期间发布**。届时再决定是停 beta 还是切 ^10.0.0。
- 评估时长:**~25 分钟**(WebSearch + WebFetch + npm/gh CLI 实测)。
