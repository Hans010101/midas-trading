# 0048 · 流量归因两个 P0 埋点 bug 修复(同域 referral 污染 + PV 预取虚高)

**日期**:2026-07-07
**状态**:已定案(Hans 核过 · 诊断先行)
**关联**:SEO 批6 度量闭环(commit 78a3596)、[[deploy-cross-race-pull-mode]] 无关

## 背景

7/5-7/6 admin 看板 PV 尖峰(峰值 ~1600 vs 基线 300-700),Hans 关注"尖峰来源 + 转化为何低"。
诊断先行、用生产真实数据(非推测),查出**两个独立的埋点 bug**(此前误当一个):

## Bug A · 同域 referrer 被误记成外部 referral(来源桶污染)

**现象**:7/5-7/6 的 `referral` 来源域名全是 `midastrade.asia`(自己的站)。

**根因**:中间件 `extractRefHost(referer, selfHost)` 本有自指剔除(`h === selfHost → null`),
但 selfHost 传的是 `req.nextUrl.hostname` —— 在 Caddy → standalone-Next 部署下,
`req.nextUrl.hostname` ≠ 公网域(常是内网 host / localhost),自指判断恒不命中 →
**每次站内跳转的同域 referer 都漏成"外部 referral (midastrade.asia)"**。
铁证:Caddyfile `header_up Host {host}` 已正确透传 apex,是代码读错了 host 来源(读 nextUrl 没读 Host 头)。

**只污染来源桶,不加 PV**(`record_source` 与 `record_visit` 是两条独立链路)。

**修复**:
- 前端 `extractRefHost` 的 selfHost 改用 `req.headers.get('host')`(Caddy 透传的真实公网域);
  两侧 host 都走 `normalizeHost`(去 www/端口)对称比较,消 apex/www 不对称漏判。
- 后端纵深防御:`classify_source(..., self_host=)` 认自有公网域(取自 `public_web_base_url`)→ 归
  `internal`,前端漏发同域 ref_host 时也不误记 referral。

## Bug B · PV 计入 Next 预取请求(PV 虚高)

**现象**:PV/UV 比 7/6 达 13.2(基线 ~5),PV 尖峰倍数远超 UV 尖峰倍数。

**根因**:埋点 beacon 只判 `GET && status<300 && !BOT_RE`,**完全不认 Next 15 的预取/RSC 请求**。
Next App Router 生产默认预取视口内所有 `<Link>` → 每个预取都是对路由的 GET → 命中中间件 →
真浏览器 UA → **触发 PV beacon**。一个链接密集的页,一次浏览被放大成十几个"PV"。
(预取灌水是**所有天的常量**、非尖峰独有 → 不制造相对尖峰,但让所有 PV 绝对值偏高。)

**修复**:中间件加 `isPrefetchRequest(headers)` —— 认 Next 15 预取头
`next-router-prefetch` / `next-router-segment-prefetch`(源:Next `app-router-headers.js` +
`fetch-server-response.js`:`prefetchKind===AUTO` 才设 `next-router-prefetch:1`,正常导航不带)
+ 浏览器 `sec-purpose: prefetch`。命中 → **不计 PV**。★**真软导航(点击)不带预取头 → 照常计 PV**。

## 历史数据口径(不追溯改写)

原始每条访问明细已弃(只留按天聚合),无法精确回补,故**不追溯改写**,改标注口径:
- **daily_visit_stat 的 PV(全历史,批6 前后皆然)**:含 Next 预取灌水、系统性偏高;修复只对**修复上线后**的 PV 生效。历史趋势**以 UV 为可信信号**(cookie 去重、预取不重复计)。
- **daily_source_stat 的 `referral`(2026-07-04 22:46 批6 上线 ~ 修复上线之间,含 7/05-07)**:
  绝大多数是自指污染(站内跳转),**作废、不代表真实外部引荐**;真实来源归因从修复上线后重新起算。
- **daily_crawler_stat**:无此问题,一直正确(爬虫独立计数、不混 PV)。Googlebot 14→60 是 SEO 抓取升温正指标。

## 真实基本盘重估(修复前用可信信号)

- 访客(UV):基线 ~30-64/天,7/05=78、7/06=119(**~2.6× 真实上涨**),7/07 半天 16。
- 结论:有真实访客上涨,但幅度是 2-3×(非 PV 显示的 6×+);PV 数字修复前一律视为偏高。
  "真人 vs 浏览器UA爬虫"最终判别 = 注册逐日(Hans 手查),尖峰日若近 0 注册则含金量低。

## 验证

- 机器验证:后端 ruff/mypy/pytest(classify_source 全矩阵 + 新 self_host 用例 36 passed);
  前端 tsc 0 error / eslint 0 / vitest 13 passed(★对照:预取不计、真软导航/硬导航计、自指剔除)。
- 生产验(上线后):PV 数字回落到真实浏览量、来源桶不再全自指(internal/direct/真实外部)。
