# 0056 · i18n 前端激活(cookie 模式 · 复活英文版 · resolve_lang 扩回)

- 日期:2026-07-16
- 状态:已采纳 · 第一阶段骨架(App 壳)· 红线级(碰语言解析 + 用户可见)
- 关联:0047(resolve_lang 收窄)· [[i18n-fullsite-bilingual]] · [[i18n-resolve-lang-narrowed]] ·
  docs/research/i18n-english-version-status-audit.md

## 背景

后端双语 100% 上线(prompts_en / language_lock / en validator / 734 键翻译库 / 事件层双语),
`X-Lang: en` 生产可出英文 AI。缺的只有前端激活——而前端有 **4 次翻车史**:
① as-needed `[locale]` 路由两次生产 redirect loop · ② SSG×[locale] 页翻倍两次撞生产内存墙 ·
③ cookie 刀2 `window.fetch` monkey-patch 转发 caller `this` → 浏览器 "Illegal invocation" 全站后端不可达。

## 决策

### 1. 架构 = cookie-locale · 无 `[locale]` 路由(重建,不续旧分支)

- 5 个历史分支 135–170 commit stale,`[locale]` 路由分支是【已废弃方案】→ **重建**,只借鉴 cookie-p1/p2 的形状。
- `i18n/request.ts` 读 `NEXT_LOCALE` cookie 定 locale;`routing.ts` 收为纯常量(去 defineRouting/localePrefix);
  `next.config` 挂 `createNextIntlPlugin`;根 `app/layout.tsx` async + `getLocale()`/`getMessages()` +
  `NextIntlClientProvider`;**middleware.ts 逐字节零改**。
- ★结构性消除两类事故:无 `[locale]` 段 = 无 redirect 重写(loop 物理不存在);无页翻倍 = 无内存墙
  (build 实测 263 静态页,未翻倍)。
- ★静态/动态:force-static / SSG 页(landing `/` / 详情 `[symbol]` / privacy/terms/risk / about)构建期
  `cookies()` 无值 → 落 zh 静态(SEO/速度零回归);动态 App 页(workbench/account/lab · 本就动态)读 cookie 出 en。
  = 记忆定的「SSG 只 zh 基线 · en 按需 dynamic」。

### 2. X-Lang 注入 = 逐 API 模块显式合并(★绝不全局 monkey-patch)

- 血证:cookie 刀2 `window.fetch = fn(){ orig.call(this,…) }` 转发非 Window `this` → "Illegal invocation"。
- 本刀:`lib/i18n/lang-headers.ts` `withLang(headers)` 读 cookie 合并 `X-Lang`,**逐 API 模块显式 threaded**
  (本阶段 ai-decision.ts)· 安全(不碰全局)、可控、可 grep。
- ★关键收益:**resolve_lang 扩回 ②(见下)使登录用户服务端自动出 en(token→user→pref)**,X-Lang 主要覆盖
  guest + 切换即时生效 → 注入面很小,不需全局拦截。

### 3. resolve_lang 扩回 level ②(language_pref)· ★与切换 UI 原子

- 0047 收窄根因=纯中文无切换 UI 时自动 en 判定用户切不回。**现有切换 UI(LanguageToggle + 设置)** →
  language_pref 由用户显式设定、可随时切回,②安全。扩回 ②(~2 行,零调用点改)。
- ★**③ Accept-Language 仍停用**——它按浏览器语言自动判 en,正是 0047 的 bug 源,坚决不扩。
  不变式:en 只来自显式动作(X-Lang / 落库 language_pref),浏览器语言绝不自动判 en。
- ★扩回 ② 必须与切换 UI 同刀,单扩无 UI = 0047 重演。

### 4. scope-A 泄漏拆分

- `composite_label`(强多/弱多…)= 5 值枚举【同时是色/逻辑 code】→ wire 恒中文,仅 display 本地化
  (前端 COMPOSITE_LABEL_KEY map · workbench.composite.* · 3 组件一致)。**本刀做**(小·低风险)。
- `chan_signals[].description` = 后端生成中文散文+价格插值 → 需改缠论共享引擎 chan.py(中等风险·红线邻近)
  → **拆下一刀**(Hans 2026-07-16 拍板)。

## 红线守住(机器验证)

- 英文 AI 红线锁全绿:validator_en 14 + econ_redline 13 + ai_decision_en 29 + i18n_lang 11 = 67 passed。
  扩回不碰任何锁,只改哪个 lang 进已测分支。
- 英文免责固定串 `"For informational purposes only and does not constitute investment advice."` 走 catalog,
  不经 LLM 翻译。不碰 prompts.py / 决策卡注入 / 交易下单。

## 验证(★真浏览器 hydrate 实测 · 非 node-sim)

- 真浏览器 /workbench:切 EN → 导航搜索/决策卡英文、`<html lang>=en`、cookie=en、URL 不变;刷新保持 en;
  切回 → zh。**全程 0 console error(无 Illegal invocation)· 无 rewrite loop · 无内存墙**。
- 生产 build 绿:✓ 263/263 静态页(未翻倍)· 类型/lint 过 · force-static/SSG 页仍静态。

## 本阶段范围(第一阶段骨架 · App 壳)

已接线:框架 + 切换 UI + resolve_lang 扩回 + X-Lang(决策卡)+ 决策卡三组件(AiDecisionCard /
CryptoAiCard / SignalBar 的技术面 + composite_label)+ 导航搜索。
批 1 续做(下批):导航链接(自选/研究室/训练营/日历)· 登录/注册页 · 设置语言 section ·
crypto 卡合约面(多空研判/实时指标)· 训练营 en coming soon · 财经日历 en 抽查。
