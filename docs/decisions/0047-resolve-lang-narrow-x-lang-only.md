# 0047 · resolve_lang 收窄为 X-Lang > zh(生产 bug 修复)

- 状态:Accepted
- 日期:2026-07-05
- 决策者:Hans(产品负责人)

## 背景 / 生产 bug

Hans 访问 `/crypto/BTCUSDT`,AI 决策卡的 LLM 生成内容(technical + plan_note)显示**英文**,
而页面其余部分中文。根因:

- `resolve_lang`(services/i18n/lang.py)是**四级优先级**:
  ① 显式 `X-Lang`/`?lang` > ② 登录用户 `language_pref` > ③ `Accept-Language` > ④ zh。
- 前端 i18n 已整体剥离(不再注入 `X-Lang`),而 i18n 刀2 短暂上线过语言切换 UI 时,
  Hans 账号的 `user.language_pref` 被写成 `'en'`;UI 撤下后脏数据留存。
- 决策卡 / 信号 / 结构诊断三处更是**直读 `user.language_pref`**(连 X-Lang 都不认),
  于是 Hans 的请求被判成 `en` → 走英文 prompt → LLM 输出英文。

## 决策

**收窄 `resolve_lang` 为二级**:① 显式 `X-Lang`/`?lang` → ④ 默认 `zh`。
**停用** ② `language_pref` 与 ③ `Accept-Language` 两级的自动判定。

理由:产品当前**纯中文、无语言切换 UI**。在没有切换 UI 的前提下,任何"自动判 en"
都是 bug 不是 feature —— 用户看到英文却无法切回。显式 `X-Lang` 保留(海外版 / 联调 / 未来
next-intl 激活时用),是唯一的自动来源。

## 保留的能力(不删)

- `translate` / catalog 双表 / en prompt(决策卡 en、结构诊断 SYSTEM_PROMPT_EN)代码**一字不删**。
- `X-Lang: en` 仍出英文(能力铁证:`curl -H "X-Lang: en"` 决策卡返英文)。
- `resolve_lang` 的 `language_pref` 入参**保留**(RequestLangDep / auth 等所有调用点签名不改)。
- 未来海外版恢复四级:在 `resolve_lang` 把 ②③ 两级扩回即可,零调用点改动。

## 实施

1. `lang.py`:`resolve_lang` 只保留 ①④,`language_pref` 入参保留但不读。
2. 决策卡 `get_decision_card` / 信号 `get_strategy_signals`(analysis.py)/ 结构诊断
   `post_diagnose`(structure.py)三处直读 `user.language_pref` → 改走 `RequestLangDep`(统一收窄口径)。
3. 数据修复:迁移 `r9s0t1u2v3w4` 重置 `language_pref='en'→'zh'`(清刀2 脏值 · 幂等 · 只碰 en 行)。
4. 缓存:AI 分析 `:en` 桶(`ai:decision:*:en` / `ai:structure:diagnose:*:en`)· TTL 自然过期;
   修后 zh 用户走无后缀桶,`:en` 桶不再被命中。可选即时清理见 PR。

## 影响面

- **zh 零变化**:所有无 `X-Lang` 的请求 → zh → 全链路原中文分支逐字节不变(覆盖现网全部用户)。
- 错误 detail(i18n 刀2/刀3):英文浏览器不再自动出英文 error(现纯中文 · 符合纯中文产品定位)。
- 红线:只改语言**选择**,不碰 prompt 内容 / engine / 交易 / 撮合;不删双语能力。
