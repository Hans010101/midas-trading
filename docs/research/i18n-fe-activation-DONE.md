# 英文版前端激活 · 第一阶段骨架 · 交付归档(DONE)

- 日期:2026-07-16 · ADR:docs/decisions/0056 · 调研:docs/research/i18n-english-version-status-audit.md
- 性质:🔴 红线级(语言解析 + 用户可见)· 点金-3 交叉审 · 复活「4 次翻车」的前端激活

## 一句话

后端双语早已 100% 上线,本刀补上「最后一公里」的前端激活——cookie 模式(无 [locale] 路由)
结构性避开历史 4 次翻车,真浏览器实测切 EN → UI/AI/免责英文、切回中文、刷新保持,全程零 Illegal invocation。

## 交付范围(第一阶段 · App 壳)

- [x] **i18n 框架**:next.config 挂 createNextIntlPlugin · request.ts 读 NEXT_LOCALE cookie ·
      routing.ts 收为纯常量 · layout async 挂 NextIntlClientProvider · **middleware 零改**。
- [x] **语言切换 UI**:LanguageToggle(top-nav · 中↔EN · 写 cookie + router.refresh · URL 不变)+
      lib/i18n/locale-cookie.ts。登录用户 PATCH /user/language 落库(端点已存)。
- [x] **resolve_lang 扩回 level ②**(与切换 UI 原子 · lang.py · ~2 行 · 零调用点改)· ★③ Accept-Language
      仍停用(守 0047 红线:浏览器语言绝不自动判 en)。test_i18n_lang 相应更新(收窄锁→扩回锁 · 仍锁 ③ off)。
- [x] **X-Lang 安全注入**:lib/i18n/lang-headers.ts withLang() 逐模块显式合并(ai-decision.ts)·
      ★绝不全局 window.fetch monkey-patch(#4 血证)。登录用户靠扩回②服务端兜底。
- [x] **composite_label 英文化(scope-A)**:COMPOSITE_LABEL_KEY map · wire 恒中文(色/逻辑 code)只 display 本地化 ·
      **3 组件一致**(AiDecisionCard / CryptoAiCard / SignalBar · 遵 CLAUDE.md「同功能多组件勿只改一处」)。
- [x] **决策卡换 key**:ai-decision-card 全量 · crypto-ai-card 技术面段 · 导航搜索。新增 catalog 键
      composite.neutral / decisionCard.{confidence,position,levelN}(zh+en 对称)。

## ★真浏览器验证(非 node-sim · 4 翻车模式逐个确认没重演)

真浏览器 http://localhost:3000/workbench 实测:
- 切 EN → 导航「Search symbols」/ 决策卡「Retry」等英文 · `<html lang>=en` · cookie NEXT_LOCALE=en · **URL 不变**。
- 刷新(整页 reload)→ 仍 en(cookie 持久 · SSR 读 cookie)。
- 切回中文 → 「搜索品种」· html lang=zh-CN · cookie=zh。
- **全程 read_console_messages = 0 error**(无 "Illegal invocation" 类浏览器运行时错)· 无 rewrite loop(URL 稳)。
- 生产 build(NEXT_PUBLIC_API_URL=prod)绿:**✓ 263/263 静态页(未翻倍=无内存墙)** · 类型/lint 过 ·
  privacy/terms/risk/about ○ 静态 · hk/us/cn/crypto/[symbol] ● SSG · workbench/account/lab ƒ 动态。

## 红线守住(机器验证)

- 英文 AI 红线锁全绿:validator_en 14 + econ_redline 13 + ai_decision_en 29 + i18n_lang 11 = **67 passed**。
  扩回不碰任何锁(只改哪个 lang 进已测分支)。
- 英文免责固定串走 catalog 不经 LLM 翻译 · 未碰 prompts.py / 决策卡注入 / 交易下单。

## 下批续做(批 1 剩余 · 非本刀)

- 导航链接(自选/研究室/训练营/日历)· 登录/注册页 UI · 设置页语言 section · crypto 卡合约面(多空研判/
  实时指标/规则解读)· signal-bar 头部(AI 信号/最近)· 训练营 en coming soon · 财经日历 en 抽查。
- ★scope-A ②:chan_signals[].description 英文化(改缠论共享引擎 chan.py · 中等风险 · Hans 已定拆下一刀)。

## 待部署 / 交叉审

- CI(lint+type+build)· 部署三件套 · 点金-3 红线交叉审(碰语言解析 + 用户可见)。
