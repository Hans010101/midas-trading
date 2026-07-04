# ADR 0045 · 训练营 URL 迁路径段 · 作废「零动态段」内部约定

- 状态:**Accepted**(产品负责人 Hans 2026-07-04 拍板 · SEO 审计决策点 D2)
- 日期:2026-07-04
- 相关:docs/seo/2026-07-seo-geo-audit.md(七镜头审计)· SEO 批2 · 0044(部署基建 · build 已挪 Actions)

## 背景

项目曾有内部约定「⛔ 不建 [id] 动态路由段 —— 走 searchParams(项目零先例)」(原
`app/academy/stage/page.tsx:4`、`app/academy/article/page.tsx:2` 注释)。该约定诞生时的动机是
避免动态段带来的构建复杂度,当时全站无 SEO 诉求。

SEO 审计(2026-07)证实该约定在训练营场景的代价:
1. **?slug= 查询参数逼出 client bailout**:stage 列表页用 useSearchParams → Suspense 空壳,
   文章 `<a>` 列表不进初始 HTML → **118 篇 SSR 完整的文章对非 JS 爬虫(=几乎所有 AI 爬虫)
   是发现不了的孤岛**(审计 critical)。
2. 文章页因 searchParams 永远 SSR(118 篇 × 爬虫抓取全部打到 7G VPS 实时渲染)。
3. 未知 slug 返回 200 软 404(不调 notFound)· 稀释抓取预算。
4. 查询参数 URL 无层级信号 · 参数变体裂变重复 URL · canonical/面包屑富结果都更脆。

## 决策

**训练营 article/stage 迁路径段,「零动态段」约定正式作废**:
- `/academy/article?slug=A2` → `/academy/article/[slug]`:generateStaticParams 118 篇**全量 SSG**
  + `dynamicParams=false`(未知 slug 构建期即 404 · 软 404 根治)+ 每篇 generateMetadata
  (独立 title/description/canonical · 告别 42/45 页全站同名)。
- `/academy/stage?s=basics` → `/academy/stage/[s]`:6 阶 SSG;StageList 去 useSearchParams 改
  props slug → **消除 bailout · 文章 `<a>` 列表进初始 HTML**(打通「首页→阶→文章」纯 HTML 爬行链)。
- 旧 URL 兜底:旧 page.tsx 转 **permanentRedirect(308)薄壳**。★Next 15 的 redirects()
  `has:[{type:'query'}]` **不支持 query 值捕获** → 薄壳是唯一正解(非偷懒)。
- 词典 `/academy/glossary#锚点` 维持单页不拆(88×250 字拆页=薄内容 · 高价值词已有整文覆盖)。

## 为什么现在做最便宜

- 站点无外链存量(robots/sitemap 2026-07 才上线)→ 迁移零权重损失;越晚做迁移成本越高。
- build 已挪 GitHub Actions(ADR 0044)→ +124 SSG 页(118 文章 + 6 阶)无 VPS 内存墙风险。
- 全库引用面实测极小:`academy/article?slug=` 3 处 · `academy/stage?s=` 4 文件 · md 正文 0 处。
- quiz/interactives/practice 注入只依赖 slug 值(key={slug}/getQuiz(slug))· 与 URL 形态无关 · 零回归。

## 约定的新边界(防未来 session 误读)

- 动态段**不再是禁区**,但仍需满足:纯静态数据源(manifest/fs)+ generateStaticParams 全量枚举 +
  dynamicParams=false。**无界动态段(如 /crypto/[symbol] 几千标的实时数据)仍不许**——那是批7
  详情页 ISR 的单独决策(D9),不在本 ADR 授权范围。
- 旧 query URL 薄壳长期保留(兜收藏/分享/外链),不设移除时间表。
