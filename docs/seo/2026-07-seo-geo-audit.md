# 点金 Midas · SEO+GEO 全站审计报告与分批优化方案(2026-07-04)

> 7 镜头并行审计(技术SEO/可爬性/结构化数据/训练营内容/GEO/性能信号/搜索接入),全部结论带实证
> (curl 生产 + 代码 grep 文件:行号 + WebSearch 2026 外部标准)。审计基线 = main 4b971f3(刀1 剥离后
> 44 页纯静态态)。★只读审计,方案 Hans 核过再分批动手。逐镜头原始报告存 scratchpad(seo_lens_*.md)。

---

## 一、总裁决:一句话诊断

**点金的内容资产(25 万字训练营 + 88 词条词典,全部服务端渲染、教科书级结构)是现成金矿,
但「矿上没有路」**:发现层三处断裂让它对搜索引擎和 AI 引擎等于不存在;全站 42/45 页共用同一个
title;GSC 未接入 = 一切优化盲飞。反过来说:**问题高度集中在"技术外壳",内容本体几乎不用动,
投入产出比极高。**

## 二、Critical 问题(7 条·跨镜头去重后 3 大主题)

### 主题 A:发现层断裂(4 个镜头同报·第一根源)
1. **robots.txt / sitemap.xml 双 404**(代码零实现·非路由问题)
2. **118 篇文章是爬虫孤岛**:文章页 SSR 完整(A2 实测 1,704 CJK 字全在 HTML),但——
   ① /academy 首页 HTML 0 个文章链接 ② stage 列表页是 client 空壳(Suspense fallback·0 链接)
   ③ 全站服务端 HTML 无任何一条指向文章的链接 ④ 无 sitemap 兜底
   → **不执行 JS 的爬虫(= 几乎所有 AI 爬虫 GPTBot/ClaudeBot/PerplexityBot)从任何页面都发现不了任何一篇文章**
3. **TopNav 全部是 `<button>` 不是 `<a>`**(市场页/训练营等一级导航爬虫不可循)· 4 市场页、
   workbench、screener 等全是孤岛页
4. **4 个 preview 详情页对爬虫 = 0 字**(BAILOUT_TO_CLIENT_SIDE_RENDERING 空壳·所有 ?symbol=
   变体字节级相同 → 长尾现状为零·塞 sitemap 也没用)

### 主题 B:元数据荒漠
5. **42/45 页共用同一 title/description/OG**(实测词典 13,480 字最大内容页和每篇文章的 title
   都 =「点金 Midas · AI 原生跨市场分析终端」)· og:url 全站指向根域 · 全站零 canonical ·
   全站零 JSON-LD · favicon 全家 404(SERP 显示灰地球)

### 主题 C:度量为零
6. **GSC 完全未接入**(代码/生产页/DNS TXT 三层查证)——收录量/搜索词/索引错误全不可见,盲飞
7. 埋点只存日级 PV/UV 裸数(**无 referrer/path/UTM**)→ 即便 Google/ChatGPT 开始导流也归因为零
   · ★附带发现:品牌词 SERP 被大量同名可疑加密站占据(midastrade.org/.net/.ltd·HYIP/CFD),
   本站零收录痕迹——尽快收录 + Organization schema 占住品牌词有紧迫性

## 三、重要利好(审计确认的地基)

- **刀1 剥离后 44 页纯静态**:TTFB 实测 ≈0.48s(纯 RTT·服务器 0ms·x-nextjs-cache:HIT)· HTML 体积健康
- **内容质量现成**:文章标题与教育搜索词天然匹配(「K线是什么」「资金费率」「三类买卖点」…)·
  词典 88 条「一句话定义+展开+关联」正是 AI 引擎最爱的 definition-lead 格式 · 免责文案已合规
- **URL 迁移面极小**:`academy/article?slug=` 全库仅 3 处引用、stage 4 文件 · **无外链存量 = 迁移零损失**
- **build 已挪 GitHub Actions(基建阶段1-4 收官)**:+118 SSG 页的构建内存顾虑已被根治,无内存墙风险
- www→apex 301 ✓ · http→https 308 ✓ · HSTS ✓ · html lang ✓ · 404 页 noindex ✓ · 8 本地字体健康 ✓

## 四、分批优化方案(按投入产出比)

| 批 | 内容 | 成本 | 依赖决策 |
|---|---|---|---|
| **批0 · Hans 亲手(仅此一批)** | ① GSC 接入:DNS TXT 域名属性(阿里云加一条 TXT·覆盖全子域)② Bing Webmaster 从 GSC 一键导入(ChatGPT 搜索 ~87% 引 Bing 索引·AI Performance 面板=GEO 官方仪表盘)③ 确认 VPS TRACK_INGEST_SECRET 已配 | 25 分钟 | 无 |
| **批1 · 发现层+快赢(一刀)** | ① app/robots.ts(allow all + disallow /account /admin /api + sitemap 指针)② app/sitemap.ts(静态页 + 118 文章 ≈130 条)③ favicon 三件(app/icon.svg + apple-icon.png + manifest.ts·素材 brand/seal.svg 现成)④ title.template + 法务三页去手写后缀 ⑤ login/register/verify-email noindex ⑥ api 子域 robots 封堵(Swagger /docs 公网 200 应挡收录) | 1 天 | 无(robots AI bot 细则待 D1·先默认全放行=现状) |
| **批2 · 训练营 SEO 主刀(金矿修路)** | ① 文章 URL 路径段化 `/academy/article/[slug]` + generateStaticParams + dynamicParams=false(118 页全静态·软404自动修·旧 ?slug= 308)② generateMetadata 每篇(title=文章题·description=excerpt·canonical)③ stage 页 server 化(列表数据本就是静态 manifest·修 hub 空壳+打通爬行链)④ /academy 首页加 server 渲染文章入口 | 1.5-2 天 | ★D2(URL 迁移·强烈建议做) |
| **批3 · metadata 铺开+结构化数据** | ① 19 个 server 页 per-page metadata(4 市场页市场化文案)+ ~8 个公开 client 页用路由段 layout.tsx 补 ② canonical + og:url 全站随写 ③ JSON-LD:Organization+WebSite(landing)· Article+BreadcrumbList(文章)· DefinedTermSet(词典 88 条)★不做 FAQPage(2026-05 富结果已全量下线)不做 Course(收益边缘) | 1.5-2 天 | D5(作者署名)D7(日期回填) |
| **批4 · E-E-A-T + GEO** | ① /about 页(是什么/方法论/为什么可信·★把合规免责升格为可引用的原则页=「合规即 SEO 资产」·文案 Hans 过目)② landing 页脚可见 mailto ③ 法务三页加更新日期 ④ llms.txt(+llms-full.txt·118 篇 md 拼接 <1MB 成本≈0)⑤ robots AI bot 显式策略 ⑥ TopNav button→Link(单独小刀·全页真机抽查) | 1-1.5 天 | D1(AI爬虫)D4(llms-full)D6(主体披露) |
| **批5 · 性能与体验(散刀)** | ① Caddyfile:XFO/Permissions-Policy/`encode zstd gzip`/public 图缓存头(371 张训练营图现 max-age=0)② next.config:poweredByHeader:false + images.minimumCacheTTL ③ 训练营图片走 /_next/image 改写(258KB PNG→30-60KB webp·零内容改动)④ klinecharts 动态导入(缓·非 SEO 主力)⑤ landing 移动汉堡(待 Hans 定性) | 1 天(④⑤另计) | D10 小项 |
| **批6 · 度量闭环** | 埋点加 referrer hostname/path/utm_source 聚合计数(google/bing/chatgpt/perplexity/direct 分桶·仍无 IP/UA/个体明细)+ AI 爬虫独立计数(GEO 领先指标)+ admin 看板来源分布 + 一次 alembic 迁移 | 0.5-1 天 | ★D8(隐私口径放宽) |
| **批7 · 详情页长尾(中期·单独立项)** | 低成本级:preview 页 server 语义壳(品种名/市场/功能说明/免责·每 symbol 唯一 title·不渲染实时数据)→ 策展池 symbol 分批进 sitemap;中成本级:ISR 渲染近收盘数据(另评估) | 低成本级 1 天;ISR 另立项 | D9(深浅+节奏) |

**建议节奏**:批0(Hans)与批1 并行本周 → 批2(金矿修路·最高 ROI)→ 批3 → 批4 → 批5/6 穿插 → 批7 中期。
每批老规矩:CI 绿待核收 → Hans 核 → 部署(走新链)→ 真机验。

## 五、决策点(需 Hans 拍板)

| # | 决策 | 选项与利弊 | 审计倾向 |
|---|---|---|---|
| **D1** | AI 爬虫 robots 策略 | A 全放行(内容=获客手段·进训练语料=模型"天生认识"点金=长期品牌复利·免费教程被复用损失≈0)/ B 放行检索类拦训练类(GPTBot/ClaudeBot/Google-Extended/CCBot 等)/ C 边缘 UA 真拦 Bytespider(连带失去豆包/头条可见性) | **A** |
| **D2** | 文章 URL 迁移 ?slug= → /academy/article/[slug] | 做:全静态+天然 canonical+软404修+SERP 面包屑·迁移面极小(3+4 处)·无外链存量=现在最便宜;不做:canonical 兜 80 分。★需正式作废「零动态段」内部约定(落 ADR 防未来 session 当违例回滚) | **做(批2)** |
| **D3** | 百度做不做 | 不做:924 通知「为境外虚拟货币业务营销宣传者依法追责」·主动提交=主动向大陆营销·百度 2021 起封加密关键词收录本就难·目标用户(港台新马)Google 压倒性;做:吃大陆流量但风险不对称 | **明确不做·无限期延后**(未来若要大陆教育流量,单独评估训练营拆独立域名) |
| **D4** | llms-full.txt(118 篇全文拼接主动供 AI) | 内容本就免费公开全量 HTML·增量暴露≈0·换被引用+品牌提及(无署名保证);诚实预期:llms.txt 采用率 ~10%·Google 明确不用·Perplexity/Anthropic 检索会读·无定量收益证据=低成本赌注 | 做(llms.txt 无争议·full 版请确认开放姿态) |
| **D5** | Article 作者署名 | 组织署名「点金 Midas 研究团队」(YMYL 可接受·匿名保护)vs 真人署名(E-E-A-T 更强·个人身份与加密内容绑定) | 组织署名起步 |
| **D6** | About 页运营主体披露度 | 只写产品与方法论(匿名延续)vs 披露注册实体(Trust 大加分·暴露在加密监管视野) | 只写产品与方法论·文案 Hans 过目 |
| **D7** | 文章日期回填 | git log 首末 commit 回填 manifest(最诚实·可脚本·但近月集中生产日期会密集)vs 不加 | 回填 + 页面可见「更新于」 |
| **D8** | 埋点隐私口径放宽 | 加 referrer hostname/path/utm 聚合计数(仍无 IP/UA/个体明细·referrer 只留域名)——是现有「隐私极简」注释的一次有意放宽 | 放宽(无第三方分析下的行业最低限度·否则 GEO 无反馈回路) |
| **D9** | 详情页长尾深浅 | 低成本语义壳(无争议)→ ISR 近收盘数据(需圈定 symbol 池如策展池/榜单前100·涉 revalidate 请求 api) | 先低成本级·ISR 另立项 |
| **D10** | 小项打包 | HSTS preload 不提交 / 完整 CSP 挂起只加 frame-ancestors / zstd 上 brotli 不上(免 xcaddy)/ sameAs 等社媒公开后再补 / Course 标记不做 / landing 移动汉堡是欠账还是取舍(定性) | 按前述默认 |

## 六、红线合规声明(全方案遵守)

所有 SEO 产出物(metadata/description/JSON-LD/llms.txt/about 文案)沿用现有合规措辞:结构描述
非建议 · 教学内容带「仅供学习参考,不构成投资建议」· 无买卖祈使词 · 终端页不出现「虚拟/模拟」
(landing/legal/about 属非终端页照旧允许)。★审计确认:现有免责体系在 YMYL 评估中是 Trust
正信号——合规即 SEO 资产,绝不为流量牺牲合规。
