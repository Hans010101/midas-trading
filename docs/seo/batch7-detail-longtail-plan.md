# SEO 批7 · 详情页长尾 · 细化方案 + 分刀计划(待 Hans 核过再逐刀实施)

> 承接调研 docs/seo/batch7-detail-longtail-research.md(#154)· 叠加 Hans 四硬约束(冲突以硬约束为准)。
> 目标:详情页从「对爬虫 0 字空壳」→ 每个(收录目标)品种有独立可搜 URL + 语义内容。

## 0. 硬约束回填(Hans 拍板 · 本方案的地基)

| # | 硬约束 | 本方案如何满足 |
|---|---|---|
| ① | 绝不 per-request SSR · 只允许 ISR 或纯静态壳 | 刀1 = **纯静态**(generateStaticParams 有界集 + 无 live 数据 → 无 ISR/无 build 期 API/无内存墙)。build 输出必须是 `●(SSG)` 非 `ƒ(Dynamic)`——这是验证靶子。 |
| ② | 渐进深浅 · 先语义壳+有限预渲染集 | 刀1 = curated 有界集(crypto Top N + 代表性股票)· 集合硬编码上界 · build 时长可控 |
| ③ | 内容红线机器化检查 | 壳文案 = **单一模板 × curated 名称**(非 per-symbol AI 生成)· 壳内**无 bias/无方向/无价格**(纯功能描述)· 免责固定 · 对抗验证 workflow 跑一遍模板+抽样渲染 |
| ④ | 壳层数据可延迟 · 实时归客户端 | 刀1 壳内**根本不放 live 数据**(只放静态名称/市场/功能说明/免责)· 实时行情仍由现有 client 组件拉 · ISR(壳塞近收盘数据)留刀2 按收录效果再评估 |

## 1. ★冲突解决(#154 倾向 vs 硬约束)

- **#154 D-a 倾向「保留 ?symbol= + server 渲染 + canonical」→ 本方案改为【路径段 `/{market}/[symbol]`】。**
  理由:query 参数(`?symbol=X`)**无法按 symbol 静态预渲染**(Next 预渲染的是路由,query 不进路由 → `/crypto-preview` 永远是【一个】静态页,不管 ?symbol);硬约束①(禁 SSR)+②(每 symbol 静态壳有独立 title/内容)**只能靠路径段 generateStaticParams**。→ 倒向 #154 的 D-b(路径段·SEO 更强·天然去重)。
- **#154 D-c/D-d**:刀1 采「有界 curated 集 + 纯静态(不做 ISR)」——比 #154「on-demand」更保守,完全落在硬约束①内。

## 2. 架构(刀1)

### 2.1 路由:additive 路径段(不动现有 app · 零回归)
- **现有** `/{market}-preview?symbol=X`(cn/us/hk/crypto-preview · client bailout · 服务【所有】symbol · 不动)——继续服务非 curated 的长尾 symbol + 旧链接,**零改**。
- **新增** `/{market}/[symbol]/page.tsx`(server component · 仅 curated 有界集):
  - `generateStaticParams()` 返回该市场 curated symbol 列表 · `export const dynamicParams = false`(非 curated → 404,不进这条路由 · 长尾仍走 `?symbol=`)。
  - 渲染 = **静态语义壳(server · 爬虫可见)** + `<Suspense><Detail symbol={symbol} /></Suspense>`(复用现有 client 详情组件 · 实时数据 client 拉)。
  - 一个页面同时满足:爬虫拿到语义骨架 + 用户拿到完整实时体验。canonical = 自身。
- **现有 Detail 组件小重构**(零行为变化):`CryptoDetail`/`SpotDetail` 加**可选 `symbol` prop**(优先 prop · 回退 useSearchParams)。`?symbol=` 页走 searchParams(现状不变)· 新路径段页走 prop。

### 2.2 语义壳内容(server 静态 · 严守红线③)
模板(单一 · 名称插值 · 无 live 数据 · 无 bias/方向/价格):
```
<h1>{name}({symbol}) · {市场中文名}行情分析</h1>
<p>{name} 的 K 线走势、缠论结构、技术指标(均线/MACD/RSI/布林)与合约数据一站式分析。</p>
<p>本页提供 {name} 的多周期 K 线图、技术面客观结构诊断与虚拟交易沙盘(全程虚拟资金)。</p>
<p class="disclaimer">⚠ 本页为结构与数据的客观展示,仅供参考,不构成任何投资建议。</p>
```
- ★**壳内绝不出现**:偏多/偏空/涨/跌预测、买卖词、具体价格、"必/稳/一定"。壳是【功能骨架】不是【行情判断】。
- ★bias(偏多/偏空/中性)是 live 数据 → 只在 client Detail 里出现(现状·已合规),**不进静态壳**。
- 机器化检查(硬约束③):对抗验证 workflow 扫【模板源码 + 抽样 N 篇渲染 HTML】· 命中买卖/预测/价格词 = 一票否决。

### 2.3 预渲染集合(有界 · D-b 名称源二合一)
新建 `lib/seo/detail-symbols.ts`:每市场 `{symbol, name}` curated 静态清单(**同时是**预渲染集合 + 语义壳名称源):
- crypto ~30 主流(BTCUSDT/比特币 · ETHUSDT/以太坊 · …)
- A股 ~15-20 代表(600519/贵州茅台 · …)· 美股 ~15-20(AAPL/苹果 · …)· HK 复用 `hk-pool.ts`(18)
- 总量 ~80-90 静态页 · **纯静态无 API · build 增量可忽略**。集合硬编码 = 天然有界。

### 2.4 sitemap + 内链
- `sitemap.ts` += curated symbol 路径段 URL(~90 条)。
- 列表/搜索/Cmd+K 对 **curated symbol** 的链接 → 指向 `/{market}/[symbol]`(内链权重导向新页);非 curated 仍 `?symbol=`。
- 旧 `?symbol=` 的 curated 重复内容风险:低(旧 client 页 0 可爬内容 → Google 不会索引/视为 thin → 有内容的路径段页胜出);**redirect/canonical 消费方全站切换 = 刀3 收尾**,不塞刀1。

## 3. 分刀计划

- **刀1 · 语义壳 + 有界预渲染(本方案主体)**:detail-symbols.ts + `/{market}/[symbol]` 静态壳 × 4 市场 + Detail 组件加 symbol prop + 壳文案模板 + sitemap 扩充 + curated 内链切换。**红线机器检查 workflow**。验:build `●(SSG)` 标记 + 44 静态页零退化 + curl 爬虫视角拿到语义内容 + sitemap 扩充。
  - ★可再切浅:刀1a = crypto + HK(名称源现成),刀1b = A股 + 美股(需 curated 名单)。视 Hans 意愿。
- **刀2 · ISR 深化(可选 · 刀1 收录见效后)**:扩大 curated 集 OR `dynamicParams=true` + ISR(revalidate 15-30min)让长尾 symbol 按需静态生成 + 壳内塞近收盘数据。**这刀才碰 ISR/build 期数据/内存墙 → 必 memory-capped 验 + 部署护栏**(见 [[deploy-build-memory-wall]])。
- **刀3 · URL 消费方收尾(可选)**:旧 `?symbol=` curated → 路径段 308/canonical 全站内链统一。

## 4. 流程(老规矩)
本方案 Hans 核过 → 刀1 写码 → CI 绿待核收 → 点金-2 交叉评审(重点:红线机器检查结果 + 零 SSR + 44 页零退化 + Detail prop 重构无回归)→ 合并部署 → 生产 curl 验证(爬虫视角语义内容 + sitemap)。

## 5. Hans 已拍(2026-07-05)
1. **刀1 一次覆盖 4 市场**(crypto+A股+美股+HK · 壳组件共享 · 加市场只多一份数据)。
2. curated 规模按默认(crypto ~30 / 股票各 ~15-18 · 总 ~80)。
3. **旧 `?symbol=` redirect/canonical 刀1 一起做**(不放刀3)。→ redirect 走 middleware 308(curated symbol · 边缘重定向不 SSR 页面不使 -preview 转 dynamic · 保「44 静态页零退化」)· middleware.ts 是点金-2 域需协调;或 client-side `router.replace` 兜底(全在 apps/web 域·旧页 0 可爬内容 SEO 损失可忽略)。实施时二选一(优先 middleware 308·协调不畅退 client)。

→ 刀1 = 一刀含 4 市场语义壳 + curated 清单 + Detail prop 重构 + sitemap + 旧 URL redirect + 红线机器检查。面较大,分文件小步 + 每步自验。
