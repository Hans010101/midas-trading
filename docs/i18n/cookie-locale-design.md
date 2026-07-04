# cookie-locale 前端 i18n 激活 · 设计文档(待 Hans 核)

> 背景:next-intl **as-needed 路径路由**方案(中文 `/`·英文 `/en`)因 middleware 隐形 rewrite ×
> NextAuth 组合**两次生产 redirect loop**(v2 cookie 检测 loop / v3 rewrite 头丢失 loop),Hans 拍板
> **废弃 /en 路径路由**,改 **cookie 切换语言 · 单一 URL 不变**。批0 v3 分支封存。本设计走 next-intl
> 官方 **"without i18n routing"** 模式。★本文档只出设计,Hans 核过再动手。

---

## 0. 一句话方案
`i18n/request.ts` 用 `cookies()` 读 `NEXT_LOCALE` 决定 locale + 载对应 messages;根 `layout.tsx` 挂
`NextIntlClientProvider` + `<html lang>`;`next.config` 挂 plugin;**middleware 零改(loop 根源物理不存在)**;
语言切换 = 写 cookie + `router.refresh()`;所有 API fetch 注入 `X-Lang` 头让后端跟随。**45 页原地不动。**

---

## 1. ★关键技术点结论:SSG × cookie 动态渲染(Hans 点名"唯一要想清的点")

**实测坐实(在当前 reverted main 上做了对照 build)**:
- 基线:**41/45 页静态预渲染**(○),只 4 页 dynamic。
- 挂 next-intl plugin + `request.ts` 读 `cookies()` + 根 layout 包 Provider 后:**静态页 41 → 4 崩塌**,
  只剩 4 个 `force-static` 页(`/`·`/privacy`·`/risk`·`/terms`)幸存,其余 37 页全变 ƒ(按需 SSR)。
- **build 本身 EXIT=0**,是干净的"被迫 dynamic",不是崩。

**机制(Next.js 官方语义 · maintainer amannn 亲证)**:`cookies()` 是 Request-time Dynamic API,
"Using it in a layout or page will opt a route into dynamic rendering"。这是 **Next.js 框架硬约束**,
非 next-intl 限制。静态渲染逃生舱 `setRequestLocale` **只在 [locale] 路由模式可用**,cookie 模式用不了。

**★但这跟批0 的死因完全不同 · 三条定心丸**:
1. **不是"本地≠生产"盲区**:dynamic 化 **本地 `pnpm build` 看 Route 输出(○ vs ƒ)就 100% 能提前发现**,
   不像 loop 那样只在生产 Caddy edge 暴露。可控、可验。
2. **不重演批0 v1 内存墙**:批0 v1 死于 `[locale]` 把 SSG 页 **翻倍 45→90** 压满 7G VPS。cookie 模式
   **不产生 [locale]×2**,页数不翻倍;且 ADR0044 已把 build 挪出 VPS(Actions→ACR→pull),内存墙物理消失。
3. **loop 根源物理不存在**:cookie 模式 **不装 next-intl 的 createMiddleware**,middleware 保持纯
   auth+埋点,不做任何 locale rewrite/307 → redirect loop 的产生条件从根上没了。

**对点金 Midas 的真实代价 = 可接受**:37 页从静态变按需 SSR,但它们都是**薄 server 壳**(数据全走
客户端 TanStack Query,SSR 不拉数据、渲染轻);生产用 **Caddy 非 CDN**(本就没吃 SSG 边缘缓存);
**无英文 SEO 需求**(Hans 已定海外走运营引流)。代价:web 容器每请求跑一遍轻量 SSR,首字节略升 —
★7G VPS 有 OOM 病史,**上线后需观测 web 容器负载**(唯一要盯的运行期指标)。

---

## 2. ★★需 Hans 拍板的架构岔路:方案 A vs 方案 B

研究浮出两条都能实现"URL 不变"的路,**选错代价大(协作铁律 §3 该问的第二类)**:

| | **方案 A · 纯 cookie 无路由(推荐)** | 方案 B · routing + `localePrefix:'never'` |
|---|---|---|
| URL 对外 | 单一 URL,永不出现 /en ✓ | 单一 URL,永不出现 /en ✓(表现完全一样) |
| 静态渲染 | ❌ 37 页转 dynamic SSR | ✅ 保留(可用 generateStaticParams+setRequestLocale) |
| middleware | **零改**(纯 auth+埋点·loop 免疫) | ⚠ 要装回 `createMiddleware`('never' 不做 as-needed 重写·loop 面小但**仍是 middleware locale 处理**) |
| [locale] 目录 | 不需要(45 页原地不动) | 要重建 `app/[locale]/` 迁 45 页 |
| 工程量 | **~8-10 文件** | 接近批0 的 65 文件重构 |
| loop 风险 | **物理不存在** | 小但非零·**需真机 Caddy 专测**(批0 就是这里栽的) |

**我的强推荐 = 方案 A**。理由:①Hans 明说"as-needed 隐形 rewrite × 中间件 = 结构性雷区,不值得付代价"
——方案 B 仍是 middleware locale 处理,**重蹈批0 覆辙的风险类别**;②无 SEO 需求 → 方案 B 唯一优势
(静态渲染/SEO)对本项目**用不上**;③方案 A 是"简单可验证"(Hans 说选型这个权重要提高);④dynamic 代价
本地 build 就能验、且已被基建根治化解。**方案 B 除非未来真要英文 SEO / 上 CDN,否则不值得。**

---

## 3. 具体接线(方案 A · 改动清单 ~10 文件)

| 文件 | 动作 |
|---|---|
| `i18n/request.ts` | **改**:`getRequestConfig(async()=>{ const c=(await cookies()).get('NEXT_LOCALE')?.value; const locale=(c==='zh'\|\|c==='en')?c:'zh'; return {locale, messages:(await import(\`../messages/${locale}.json\`)).default}; })` |
| `app/layout.tsx` | **改**:async + `const locale=await getLocale()` + `<html lang={locale==='en'?'en':'zh-CN'}>` + 最外层包 `<NextIntlClientProvider>`(Provider 从 Server Component 渲染**自动继承** locale/messages·无需传 props)。★保留现有字体 className/suppressHydrationWarning/color-pref 首屏脚本 |
| `next.config.ts` | **改**:挂 `createNextIntlPlugin('./i18n/request.ts')`(redirects 不动) |
| `i18n/routing.ts` | **精简**:去 `localePrefix`/`localeDetection`(路由专属),只留 `locales`/`defaultLocale`/`Locale` 常量供 request.ts 复用(或内联删除) |
| `i18n/navigation.ts` | **删**:createNavigation 只为剥/补 /en 前缀·无路由无消费方 |
| `middleware.ts` | **零改**(★写进设计防未来手贱·loop 根源) |
| `components/layout/language-toggle.tsx` | **新增/改**:仿 `theme-toggle.tsx`(mounted 占位防 hydration 闪)· 切换=写 `NEXT_LOCALE` cookie + `next/navigation` 的 `router.refresh()`(**不再 `router.replace({locale})`**)· 登录态仍 `setLang.mutate(next)` 写回后端 |
| `components/settings/language-section.tsx` | **新增/改**:同上·挂进 `app/account/profile/page.tsx`(与 ThemeSection/ColorPrefSection 并列) |
| `hooks/use-me.ts` + `lib/api/me.ts` | **恢复**:`useSetLanguage`/`setLanguage`/`language_pref` 字段随批0 被 revert 了·需加回(后端 `PATCH /user/language` + `language_pref` 列**仍在·零改**) |
| `messages/{zh,en}.json` | **补键**:`settings.settings.language` 全套(_/description/zh/en/note)· 否则设置页露原始 key 串 |
| `lib/api/*.ts`(统一 fetch 封装) | **改**:所有 API fetch 注入 `X-Lang: <locale>` 头(见 §4) |

**cookie 规格**:`NEXT_LOCALE`·`Path=/`·`Max-Age=1年`·`SameSite=Lax`·**非 HttpOnly**(客户端要能写)。
★不要用 session cookie(批0 靠 next-intl 自动写的是 session 级·关浏览器丢语言)。

---

## 4. 后端一致性(★必须同批做·否则半拉子)

后端 `resolve_lang` 四级优先级 **已 LIVE**:`?lang`/`X-Lang` 头 > 登录 `language_pref` > `Accept-Language` > zh。
但**后端读不到前端的 NEXT_LOCALE cookie** → 前端所有 API fetch **必须注入 `X-Lang: <当前 locale>` 头**,
否则出现"界面英文但 AI 决策卡 / 错误提示 / 策略 reason 全是中文"的割裂(典型"报告上线但用户看到半拉子",
CLAUDE.md 翻车范式)。建议在**统一 fetch 封装处**注入(读同一 cookie),不逐个 client 改。

---

## 5. locale 优先级落地(cookie > language_pref > zh)

`getRequestConfig` 是纯服务端请求配置,**拿不到 NextAuth current_user**(要查 session/DB)。落地建议(推荐 A):
- **request.ts 只读 cookie**(保持纯粹·不把 DB 读进渲染路径·避免放大 dynamic 面)。
- **登录跨设备同步** = 登录成功 / `useMe` 拿到 `language_pref` 后,若与 cookie 不一致则**客户端写 cookie + refresh**
  (类似现有 `color_pref` 首屏脚本范式)。即:language_pref 灌进本设备 cookie,之后全走 cookie 单一真相源。
- 未登录/无 cookie → fallback **zh**(★中文零破坏)。

---

## 6. 工作量 vs 批0 · 拆刀建议

**工作量**:批0 v3 = **65 文件**大重构(45 页移目录+middleware 重写+layout 重构);本方案 **~10 文件**(45 页
原地不动·middleware 不碰·6 个 nav 组件不碰)——**大幅缩小 ~6.5 倍**。

**拆 2 刀**(不宜 1:地基+UI 混一起 build 报错难定位;不宜 3+:方案够小):
- **刀1 · 激活地基(验渲染不破)**:request.ts 读 cookie + 根 layout 挂 Provider/`<html lang>` +
  next.config 挂 plugin + 删 navigation.ts/精简 routing.ts。**不加任何 UI**。验:**中文默认逐字节不破 +
  `pnpm build` 通过(看 ○/ƒ 输出确认符合预期)+ 无 redirect + 4 个 force-static 页仍 build 成(回落 zh)**。
- **刀2 · 语言切换 UI + 后端同步**:language-toggle(顶栏)+ language-section(设置页)+ 恢复
  use-me/me.ts 的 setLanguage + 补 messages language 键 + **API client 注入 X-Lang**。验:**切 EN 生效 +
  切回 + 硬刷保持 + 登录跨设备同步 + 触发后端错误(如 401)文案跟随 X-Lang**。

---

## 7. 端到端验证清单(部署后必逐项真机验)

★新方案**根本不产生 redirect**(单一 URL),但仍要按批0 翻车教训逐项验:
- (a) 未登录 `/` 默认中文 · 切 EN → cookie 写入 + 刷新变英文
- (b) 关浏览器重开语言保持(验 max-age 生效·非 session cookie)
- (c) **★curl / 健康检查裸请求(无 cookie)访问 `/` 不再 307 loop**(批0 精确复发点·必验·不能只验浏览器)
- (d) 登录用户切语言 → `PATCH /user/language` 成功 + 换设备登录语言跟随
- (e) **触发后端错误(401/额度超限/AI 决策卡)确认文案跟随 X-Lang**(半拉子检测)
- (f) middleware 的 auth 保护 + PV/UV 埋点仍正常(未被波及)
- (g) **web 容器负载观测**(37 页转 SSR 后·7G VPS OOM 病史)
- 部署走**新链**(Actions build→ACR→VPS pull·内存墙物理不存在)

---

## 8. 待 Hans 拍板的决策点

1. **★方案 A vs B**(架构岔路)—— 我强推 **A**(纯 cookie·middleware 零改·loop 免疫·~10 文件)。
2. **接受 37 页转 dynamic SSR?** —— 我判**可接受**(薄壳·Caddy 非 CDN·无 SEO·本地 build 可验·非盲区),上线后观测 web 负载。
3. **4 个 force-static 页(/·privacy·terms·risk)** —— 建议**保留 force-static·暂 zh-only**(英文版是批4·现在不订阅 locale·build 实测能过)。
4. **登录→cookie 同步** —— 建议**客户端写**(request.ts 保持纯 cookie·不读 DB)。
5. **X-Lang 后端一致性本刀纳入?** —— 强烈建议**纳入刀2**(否则半拉子)。
6. **本次 = 只地基+切换 UI·零可见文案翻译?** —— 建议**维持 Phase0 边界**(中文逐字节不变·组件换 key 是后续批1-5)。
7. **英文 SEO 硬伤知情**:cookie 单 URL 下爬虫(无 cookie)恒拿 zh → 英文对搜索引擎不可见。★Hans 已定"英文 SEO 现阶段非需求"→ **与本方案一致·非问题**(仅确认知情)。
