# 0049 · X 短推免责精简『不构成投资建议』(Hans 授权的有意偏离 · 勿当红线回归)

**日期**:2026-07-08
**状态**:已定案(Hans 明确授权 · PR #171 · commit 9220043)
**关联**:[[x-publish-adapter-live]]、X 短推 step1(#170)、X 发布接入(#169)、
范式同 docs/decisions/0011·0012 与 landing 免责移除([[landing-disclaimer-removed-authorized]])

## 背景

X(推特)短推是点金 Midas 的**营销社交文案**(≠ 产品 AI 输出)。首发(@Hanspan007 真机验完 #170)后,
Hans 提「文案更口语化」改进(改进2)。口语化 + X 免费层 110 中文字上限,使原免责全句
『仅供参考,不构成投资建议』在一条大白话短推末尾显得偏长偏正式。Hans 审改进2 时拍板:
**X 短推尾巴免责精简为『不构成投资建议』**(去『仅供参考』,只留法律核心)。

本 ADR 记录这是**Hans 授权的、有意为之的 scoped 偏离**,给未来 session 立一道明确警示线,
**防止把『仅供参考』当红线回归擅自加回**(landing 免责曾吃过这类「误当回归恢复」的亏,见 0011/0012)。

## 决策(5 点)

1. **CLAUDE.md 红线基线**:产品 AI / 策略 / 交易【输出】(决策卡 / AI 分析 / 策略信号 / 缠论 /
   周报 / 复盘 / bot)必带**完整免责**『仅供参考,不构成投资建议』——**此红线一个字不动、照旧锁死**。

2. **X 短推精简(经 Hans 授权)**:X 短推(`gen_style=x_short`)尾巴用**『不构成投资建议』**
   (去掉『仅供参考』前缀,保留法律核心「不构成投资建议」)。
   原因:① X 传播需精简犀利;② X 免费层 110 中文字上限,免责越短越给正文让空间。

3. **Scope 严格限定 `x_short`**:只改 `tweet_gen.py` 的 `_SYSTEM_X_SHORT` + `build_user_prompt`
   的 x_short 分支。**决策卡 / AI分析 / 策略信号 / 缠论 / 币安长文(default)/ 周报 / 复盘 / bot
   全部保留完整免责『仅供参考,不构成投资建议』**——精简不外溢一寸。
   (测试 `test_x_short_disclaimer_shortened_gate_still_passes` 断言 default 仍全句,钉死不外溢。)

4. **门禁仍强制**:X 合规门禁 `compliance.py:validate_tweet` 的 `_DISCLAIMERS` token 集合含
   『不构成投资建议』(六之一),`any-present` 判定 → 只带『不构成投资建议』的推
   `validate_tweet().passed=True`(已 venv 实测)。门禁只『缺了拒』**无兜底回填**
   (不会把『仅供参考』自动加回)。★免责【没删,只精简】,红线本质(必带免责声明)不变。

5. **★★给未来 session 的明确警示**:X 短推末尾无『仅供参考』= **有意为之的产品决策**,
   **勿当红线回归、勿擅自把『仅供参考』加回 x_short**。若要恢复,须 Hans 重新授权。
   (同 [[landing-disclaimer-removed-authorized]] 范式:营销层免责调整,经授权,勿误当回归恢复。)

## 边界澄清(一句话)

**营销文案(X 短推 / 币安广场)的免责措辞可经 Hans 授权微调;产品 AI 输出(决策卡等)的免责红线
锁死不动。** 本次动的是前者的 x_short,后者一个没碰。

## 验证 / 落地

- 实现:PR #171(commit 9220043)· CI 双绿 · 8 镜头红线对抗审查 0 确认问题 · 点金-3 免责精简复扫 CLEAN。
- 部署:merge bed5a7d · 三件套过(Actions 绿 + docker 真重建 api/worker/web + 生产 curl 健康)。
- 测试锁:`tests/services/test_x_compliance.py::test_x_short_disclaimer_shortened_gate_still_passes`
  (x_short 尾巴精简 + default 仍全句 + 门禁认『不构成投资建议』token)。
- 记忆:[[x-publish-adapter-live]] 已固化「改进2 免责精简」段。

## 待办(非阻塞)

CLAUDE.md 「红线」章仍写全句『仅供参考,不构成投资建议』。可选:在 CLAUDE.md 红线处加一行注明
「X 短推营销文案例外(见 ADR 0049)」,让基线文档与本 ADR 显式对齐。本 ADR 已足以立警示线,
CLAUDE.md 注明与否由 Hans 定。
