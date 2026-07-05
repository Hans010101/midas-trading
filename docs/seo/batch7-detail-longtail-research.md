# SEO 批7 · 详情页长尾方案(调研 only · 待 Hans 决策 · 不实施不部署)

> 审计决策点 D9 定案:先低成本语义壳,ISR 另立项。本文出方案供 Hans 拍板深浅与节奏。
> 前置:批1(sitemap)/批2(训练营路径段)/批3(metadata+JSON-LD)已上线,详情页是最后一块长尾。

## 一、现状(审计实测 · 铁证)

4 个详情页 `/{cn,us,hk,crypto}-preview?symbol=X` 对爬虫 = **0 字空壳**:
- 结构:`app/{m}-preview/page.tsx` = `<Suspense fallback={<main/>}><{M}Detail/></Suspense>`,
  Detail 组件 `'use client'` + `useSearchParams()` 读 `?symbol=` → SSG 时整页 bailout
  (`BAILOUT_TO_CLIENT_SIDE_RENDERING`),server HTML 只有空 `<main>`。
- 后果:① 非 JS 爬虫(几乎所有 AI 爬虫)看不到任何行情/分析内容;② 所有 `?symbol=` 变体
  返回**字节级相同**的空壳(同 title/同 description),Google 去重合并;③ 个股/币种长尾搜索
  (「600519 分析」「BTCUSDT 资金费率」)当前收获 = 0。
- ★这不是加 sitemap 能解决的(空壳 URL 大批量进 sitemap 反伤站点质量)——需架构改造。

## 二、两级方案

### 低成本级:server 语义壳(无争议 · 建议先做)

**做法**:preview 页改「server 读 symbol + 渲染一段静态语义描述」,真实行情/AI 数据照旧 client 拉。
- server 端只渲染:品种名 + 市场 + 该页能做什么(K线/指标/缠论/AI 决策卡)+ 免责语。
  ★**不渲染实时行情数字**(避免 SSG/ISR 缓存过期数据 + 红线:不预测)。
- 爬虫至少拿到:`<h1>贵州茅台 600519 · A股 K线与结构分析</h1>` + 一段功能说明 + 唯一 title
  `贵州茅台(600519)· 点金 Midas`。
- 实现:仿批2 —— server 页读 params/searchParams(server 端),渲染语义壳 + 挂 client 的
  Detail 组件(数据部分)。**symbol → 名称映射是唯一前置**(见决策点 D-b)。

**收益**:每个 symbol 页有唯一 title + 语义内容 + 可被独立收录;从 0 到 1。
**成本**:~1 天(不含 symbol 集合圈定);**风险低**(不碰实时数据 · 不碰引擎)。

### 中成本级:ISR 渲染近收盘数据(另立项 · 有代价要拍板)

**做法**:`export const revalidate = 300` 之类,ISR 时 server 调 `api.midastrade.asia` 拉最近
收盘价/涨跌幅渲进 HTML(爬虫拿到带真实数据的页)。
**代价**(D9 需拍板):
1. **构建/revalidate 内存墙**(deploy-build-memory-wall 前科):ISR 首次渲染 + 周期 revalidate
   会在 web 容器请求 api,与「构建产物膨胀撞生产内存墙」同域 → 需 memory-capped 验证。
2. **symbol 集合爆炸**:A股 5000+/美股数千/港股/加密全量预渲染不现实 → 必须圈定
   「预渲染哪批 symbol」(如策展池 / 各市场榜单前 100),其余 on-demand ISR。
3. 数据时效:ISR 缓存窗口内数据陈旧(revalidate 周期权衡)。

## 三、决策点(需 Hans 拍板)

| # | 决策 | 选项 | 建议 |
|---|---|---|---|
| **D-a** | URL 形态 | A 保留 `?symbol=` + server 渲染 + canonical(改动小·query 弱势但可用)/ B 迁路径段 `/crypto/[symbol]`(SEO 更强·天然去重·但全站内链/收藏迁移 + 301 · 面大) | A 先行(低成本级用 A)· B 若做 ISR 一并评估 |
| **D-b** | symbol → 名称映射源 | server 语义壳需 symbol→中文名+市场:加密 pair 自解释(BTCUSDT)· A股/港股需映射(hk-pool.ts 有港股池·cn 名称在 api/静态表?)· 需确认是否有现成静态源,否则 server 端调 api(引入渲染期依赖) | 落地前先盘 symbol 元数据源(可能需建静态表) |
| **D-c** | 预渲染 symbol 集合 | 低成本级:全量 on-demand(dynamicParams=true·无预渲染压力)/ 中成本级:圈策展池 or 榜单 top N 预渲染 | 低成本级 on-demand · 中成本级圈 top 100 |
| **D-d** | ISR 做不做 / 何时 | 不做(只低成本语义壳)/ 做(需 memory-capped 验 + symbol 集合圈定 + 单独一刀) | 先只低成本级 · ISR 观察低成本级收录效果后再评估 |

## 四、建议节奏

1. **低成本语义壳**(D-a=A · D-b 盘清 symbol 源后):独立一刀 · 4 个 preview 页 server 语义壳 +
   每 symbol 唯一 title/canonical + 进 sitemap(策展池 symbol 分批)。风险低 · 是 D9 的「先做」。
2. **ISR**(D-d):等低成本级上线 + GSC 看收录效果,再决定是否值得承担内存墙 + symbol 集合复杂度。
   ★属「本地≠生产」内存墙高风险区,必 memory-capped docker build 验 + 部署护栏。

## 五、红线

语义壳文案:结构描述非预测 · 免责 · 无买卖祈使词 · 终端页不出现「虚拟/模拟」(preview 是终端页)。
★绝不 server 渲染伪造/过期的行情数字(CLAUDE.md 红线:接不上一律占位「—」· 绝不伪造)。

---
**结论**:低成本语义壳无争议、风险低、是 D9 的「先做」项,但需先盘清 symbol 元数据源(D-b);
ISR 是高价值高风险的中期项,建议低成本级上线看效果后再拍。**本文调研 only · 待 Hans 决策后再立刀。**
