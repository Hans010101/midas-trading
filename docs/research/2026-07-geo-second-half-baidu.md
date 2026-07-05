# GEO 下半场 + 百度重评估 · 调研报告(2026-07)

> 4 维度并行调研(国内 AI 引擎可发现性 / 百度半站策略 / 海外 AI 引擎巩固 / 内容 AI 可引用性)。
> 纯调研文档,未改任何代码。Hans 2026-07-05 核收定案(见文末「决策定案」)。
> 战略意图:大陆中文流量【主攻被豆包/Kimi/AI 引用,放弃百度自然排名】;训练营 A/B/C/F 通用交易知识接大陆 AI 视野。
> 🔴 红线:加密内容绝不进大陆视野;投资免责不动;匿名保护。

---

## 三个颠覆认知的发现

1. **llms.txt 对国内 AI 引用 ≈ 零杠杆**。国内豆包/文心/Kimi/DeepSeek 无一家认 llms.txt;全球 97% 的 llms.txt 收零 AI 请求,Google 明确不支持(Mueller 类比已废弃的 keywords meta)。真正有用只剩 Perplexity 排序 + IDE/MCP agent 抓取。→ 保留无妨(成本沉没),停止追投。

2. **国内 AI 引擎大半是观测盲区**。我方 classifyCrawler 只能看到字节(Bytespider)+ 百度(Baiduspider)两条 UA。DeepSeek/Kimi 走**博查 Bocha Search API**(承接国内 60%+ AI 联网检索,日调用 3000 万+),抓取无自报 UA → 永远看不到。**绝不能用「看板没流量」推断「没被引用」**。★关键推论:被 DeepSeek/Kimi 引用 = 被博查/**Bing** 收录 → 我方已接 Bing WMT = **这条暗门已通**。

3. **★最大红线冲突**:当前 `robots.ts` 全放行 + `sitemap.ts` 含 `/crypto-market`(0.8 权重)。一旦向百度提交 sitemap = 主动把加密内容推进大陆视野 = 违反红线。且训练营阶段映射与直觉不符:

   | 阶 | slug | 内容 | 百度安全? |
   |---|---|---|---|
   | 一 | `basics` | K线/做多做空/杠杆… + **A10 四市场含加密 · A11「加密为什么以合约为主」** | ⚠️ 需按文章 allowlist |
   | 二 | `technical` | 均线/MACD/布林/RSI | ✅ 通用 |
   | 三 | `chan` | 缠论 | ✅ 通用 |
   | 四 | `contract` | **永续合约/资金费率/爆仓强平**(= 直觉里的「E 阶」) | ❌ 加密核心 |
   | 五 | `strategy` | 策略(网格/马丁格尔…) | ✅ 大部分通用 |
   | 六 | `system` | 交易体系/心理/复盘 | ✅ 通用 |

   → 百度过滤必须**按文章 allowlist**,不能按阶段(basics 里就有加密文章)。

---

## 维度 1:国内 AI 引擎可发现性

- **豆包(字节)**:自建爬虫 **Bytespider**(既抓训练语料也建 AI 搜索索引),四家里唯一真跑自建全网爬虫;我方已识别。声称遵守 robots 但实测时好时坏、多变体。2024→2025 爬虫流量占比 42%→7%。〔high〕
- **DeepSeek**:联网搜索**不靠自建爬虫**,调博查 Bocha Search API;不公开任何 UA,抓取伪装浏览器 → 我方看板观测不到。〔high〕
- **Kimi(Moonshot)**:内置 web_search 工具;Kimi-User 爬虫伪造 UA(出现过 Windows NT 11.0),不自报身份;联网大概率也走第三方搜索 API。〔medium〕
- **文心一言(百度)**:检索增强直吃百度搜索自有索引(百度既是搜索引擎又是模型厂),靠 Baiduspider。**四家里唯一「索引=大陆主搜索引擎」、唯一能靠传统 SEO(百度收录)撬动**的入口。〔high〕
- **博查 Bocha = 国内 AI 搜索的隐形底座**:DeepSeek 官方 + 阿里/腾讯/字节推荐的 Search API,承接 60%+ AI 联网检索,索引近百亿网页。DeepSeek/Kimi 能否引用我方内容 = 博查有没有收录,与我方 robots/llms.txt 无关。〔medium〕
- **可观测性**:daily_crawler_stat「AI 爬虫」卡对国内引擎真实覆盖只有【字节+百度】两条;DeepSeek/Kimi/博查系全盲区。〔high〕
- **llms.txt**:国内四家均无公开声明支持;百度/字节收录靠传统爬虫+结构化数据(Article Schema 时间戳),不是 llms.txt。〔high〕
- **被引用真实路径**(无一经 llms.txt):① 进大陆搜索索引(百度→文心、博查→DeepSeek/Kimi、Bing→部分兜底);② 被 Bytespider 抓;③ 结构化+权威信号(时间戳、EEAT 2.0、高权重站引用)。实时检索型(博查/Bing)门槛最低响应最快;训练语料型是长期复利但滞后不可控。〔medium〕
- **境外无 ICP 站百度收录**:不等于技术上不能收录,但青睐度低、更慢、排名劣势;百度搜索资源平台可提交(靠站点验证,无明文禁境外),但收录≠好排名。〔medium〕

来源:ai-bot.cn/bytespider · cloudflare 2025 crawler 报告 · 36kr/新浪(博查) · open.bochaai.com · ppc.land/ahrefs(llms.txt) · developer.baidu.com · ziyuan.baidu.com

## 维度 2:百度「半站策略」技术评估(境外无备案站 ROI)

- **Next.js robots.ts 多 userAgent 段可落地**:`rules` 可为对象数组,每段独立 userAgent + allow/disallow。新增 `{ userAgent:'Baiduspider', allow:[...], disallow:[...] }` + 保留 `{ userAgent:'*', ... }` 兜底(其它爬虫维持全放行)。★爬虫只遵守与自己 UA 最匹配的段 → Baiduspider 段必须**自包含全部 disallow**,不继承 `*` 段。建议 Baiduspider + baiduspider 两大小写都写。〔high〕
- **robots 是君子协定**,不是访问控制 → 真硬隔离需叠加页面级 noindex(Baiduspider UA 下)或后端按 UA 拒服。〔medium〕
- **百度账号注册门槛**:强制手机号实名,官网注册页只接受**大陆手机号**;海外号需走「先用海外号注册百度公有云/好看/小度/apollo 之一,再回站长平台登录」迂回(香港/美国号已验证可行,欧盟号不行)。〔high〕
- **站长验证与 ICP**:验证所有权(文件/HTML 标签/CNAME)**不要求 ICP 备案**;备案只在申请「新站保护」(前期收录加速)时被要求。无备案=拿不到新站保护=前期收录更慢,但不是收录必要条件。〔high〕
- **无备案境外站收录现实**:香港服务器免备案上线;百度口径称一视同仁、备案非排名因子;但新站期无新站保护→收录更慢、更依赖内容质量;纯前端 SPA 抓取本就弱。〔medium〕
- **midastrade.asia 当前收录**:百度对自动化 `site:` 查询直接 302 到验证码墙(拿不到准数);西方引擎 `site:midastrade.asia` 零命中我方页面(全是同名他站)。综合推断百度侧当前收录极可能为 0 或极少,需人工登站长平台「索引量」坐实。〔medium〕
- **豆包线 ≠ 百度线**:豆包走 Bytespider(已被 `*` 全放行),接豆包/AI 入口**不依赖百度收录**,当前已具备。百度半站只服务「百度大陆中文搜索流量」这条窄线。〔high〕

来源:nextjs.org robots 文档 + baidu.com/robots.txt(其自身即 per-UA 段)· extrabux(海外号注册)· ziyuan.baidu.com/college · 知乎/华纳云(无备案收录)

## 维度 3:海外 AI 引擎巩固

- **实测限制**:subagent 只有 WebSearch(US 网页检索),无法编程访问 ChatGPT/Perplexity/Claude → 唯一可靠实测 = 人工每周用固定问题问引擎看引用。〔high〕
- **当前外部可见性(硬事实)**:搜「midastrade.asia 点金 Midas」全是同名 forex/crypto 站(midasglobal.net/midastrade.org…至少 6 个),**没有一条是我方**。品牌名撞车严重 = GEO 先天劣势。真实状态是「尚未进入可被引用的池子」而非「巩固」。〔high〕
- **Perplexity 机制**:6 阶段 RAG,检索 5-10 页只引 3-4 个,过五道闸;偏爱可整段抽取的体裁(定义/数字/对比/步骤)= 对上我方 definition-lead 词典;**确实检索 llms.txt 用于排序**(少数用它的引擎)。中文覆盖弱于 Kimi。〔high〕
- **★Bing AI Performance 面板**:Bing Webmaster Tools 2026-02 上线,展示站点被 Copilot/Bing AI 引用数据(引用数、被引 URL、grounding queries);2026-06 加 Citation Share。**唯一免费官方能真观测「进没进 AI 答案」的入口**。前提:Bing 验证 + 提交 sitemap + IndexNow。〔high〕
- **Bing Copilot 引用硬前提**:① 被 Bing 索引且对 query 有排名;② 页面是最清晰可抽取答案。allow Bingbot 即够(我方 robots `*` 已放行)。〔high〕
- **definition-lead 词典优势**:方向对但是「结构合格」非「赢面大」——满足 Layer 1(可抽取)是入场券,被不被引还取决于**共识信号**(多个独立来源一致出现);我方纯自有站零外部佐证 = 共识信号最弱档。〔high〕
- **域名结构现实锚点**:Reddit/Wikipedia 是 LLM #1-2 被引域名;.com 占 80%+;但头部合计也少超 5%,95% 引用散在数千域名的长尾 → 新独立站要挤长尾,中短期海外引用份额趋近零。〔high〕

来源:blogs.bing.com(AI Performance)· authoritytech/ziptie(Perplexity)· limy.ai/allmo(llms.txt 无相关性)· Contently/Similarweb(被引域名)

## 维度 4:内容 AI 可引用性增强空间

- **AI 抽取单元 = passage/chunk**:40-75 词(中文 60-120 字)自足答案块被引概率是长段落 3.1 倍;BLUF/answer-first(H2 下先给自足答案)最受偏好。〔high〕
- **★我方词典 88 条 definition-lead = 教科书级正确**:每条 `**一句话定义:**` 开头,自足单段可整块抽取。我方 AI 可引用性最高资产,几乎无需改。〔high〕
- **118 篇文章已有「本篇要点」总结块,但在文末(位置次优)**:5-6 条 bullet、质量高、已是自足 chunk,但在最底部;answer-first 最佳实践是放 H1 之后正文之前。**好素材放错位置**。〔high〕
- **FAQPage schema**:Google 富结果已下线(2023 限权威站/2026-05 全量),但**AI 引擎仍重度解析**(Perplexity/ChatGPT/Gemini/AI Overviews 当抽取信号)。给 Google 富结果看=无收益;给 AI 抽取看=仍有收益。〔high〕
- **JSON-LD = 间接放大器**:AI 不逐字复述但让实体/关系可直接抽取;带有效结构化数据的页在 AI 摘要出现频率高 20-30%(供应商基准需打折)。〔medium〕
- **★我方 Article JSON-LD 缺 datePublished/dateModified**:`lib/seo/schema.ts` buildArticleSchema 有 headline/description/author(「点金 Midas 研究团队」匿名)/publisher/image,但注释「无日期,git 回填是后续小刀·宁缺毋假」= 当前 schema 最明显缺口。〔high〕
- **AI 抓取基建已闭环**:robots 全放行 + classifyCrawler + daily_crawler_stat + llms.txt → 任何增强改动可用现成爬虫命中曲线前后对照。〔high〕

来源:stackmatix/writesonic/lumar(chunk)· git show glossary.md/schema.ts(我方实测)· searchenginejournal(FAQ 下线)· thegrowthgpt/brightedge(JSON-LD)

---

## 分级行动建议汇总

**🟢 立即做**:接 Bing WMT+IndexNow〔D3·Hans 已完成〕· 重定位 llms.txt 预期〔D1〕· **文章顶部 TL;DR 前移**〔D4·最高性价比〕· JSON-LD 补 date〔D4〕· 人工 AI 引用监测〔D3〕
**🟡 值得做**:robots Baiduspider 段(技术就绪·留档不实施)〔D2〕· FAQPage schema 试点(只 A/B/C/F+非加密)〔D4〕· 解决品牌撞车主打「点金 Midas」实体〔D3〕· 词典自足性微调〔D4〕
**🔴 不值得做**:ICP 备案〔引火烧身+加密撞红线〕· 付费 AI 引用 SaaS〔现零引用〕· HowTo schema〔误标〕· 追百度富结果 · 更多 llms.txt 变体

---

## 决策定案(Hans · 2026-07-05)

1. **★战略取舍**:大陆流量**主攻 AI 引用、放弃百度自然排名** —— 定。
2. **Bing WMT**:Hans **早已接入**(批0 从 GSC 导入)—— 已完成。→ 维度 2 发现的「暗门」(DeepSeek/Kimi 走博查/Bing)已通。
3. **百度侧整体暂停**:不提交 sitemap、crypto 隔离工程**不做**(本文档「百度隔离方案」留档,将来真投百度再启动)、不注册百度站长、**ICP 明确否决**。
4. **人工 AI 引用监测**:轻流程记档即可(定期问 ChatGPT/Kimi 固定问题)—— **不做付费 SaaS**。
5. **执行项两个**(按序):① 本调研报告归档;② **TL;DR 前移刀**(118 篇顶部 answer-first 要点块 + JSON-LD 补 date)。**FAQPage schema 试点先停靠**(TL;DR 见效后再议)。

---

## 百度隔离方案(留档备用 · 将来真投百度再启动 · 当前不实施)

若将来决定投百度,动手前**必须先**完成 crypto 大陆隔离(否则绝不 submit sitemap):

1. **robots.ts 改数组 + Baiduspider 专属段**:
   - `{ userAgent: ['Baiduspider','baiduspider'], allow: ['/academy','/about', ...通用页], disallow: ['/crypto-market','/crypto-preview','/crypto/', ...所有 crypto 路径] + [第四阶 contract 全部文章 slug] + [basics 里 A10/A11 等涉加密文章] + [/account,/settings,/portfolio,/dashboard,/admin,/api/] }`
   - 保留 `{ userAgent: '*', allow: '/', disallow: [现状 6 条] }` 兜底(豆包/海外 AI 维持全放行)。
   - ★Baiduspider 段**自包含全部 disallow**(不继承 `*`)。
2. **页面级硬隔离**:crypto 页在 Baiduspider UA 下输出 `<meta name="robots" content="noindex">` 或后端按 UA 拒服(robots 只是君子协定)。
3. **百度专用 sitemap 变体**:剔除所有 crypto 路径 + 第四阶/涉加密文章,只提交 A/B/C(除涉加密)/五/六 通用交易知识。
4. **按文章 allowlist**(非按阶段):因 basics 阶含 A10/A11 加密文章,过滤粒度必须到单篇。
5. llms.txt 若含第四阶加密文章,面向大陆 AI 生态同样复核(主抓手仍是 Baiduspider robots + 页面 noindex)。

---

## 红线(锁死 · 任何 GEO 动作遵守)

1. **加密内容绝不进大陆视野**:TL;DR/FAQPage schema/llms.txt 摘要等所有「更易被抽取」的增强,**只作用于 A/B/C/F 通用交易知识 + 非加密词条**;第四阶 contract、词典加密专属词条(合约/永续/资金费率…)不进面向抽取的 schema/摘要。
2. **投资免责不动**:TL;DR/schema description 沿用「教学内容,仅供学习参考,不构成投资建议」;TL;DR 块不得出现买卖祈使或价格预测。
3. **匿名保护**:JSON-LD author 维持「点金 Midas 研究团队」,补 date 不引入任何个人身份信息。

后续动手参考文件:`apps/web/lib/seo/schema.ts`(buildArticleSchema 补 date)· `apps/web/content/academy/articles/*.md`(TL;DR 前移)· `apps/web/content/academy/glossary.md`(88 条 definition-lead 维持)· `apps/web/components/academy/article-renderer.tsx`(顶部块渲染)· `apps/web/app/robots.ts` / `sitemap.ts`(百度隔离·留档不动)。
