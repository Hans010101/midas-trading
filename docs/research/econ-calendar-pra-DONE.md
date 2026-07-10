# 财经日历页 PR-A · 交付归档(DONE)

- 日期:2026-07-10
- PR:#186 · 决策:docs/decisions/0052 · 上一刀:P0(#185 · ADR0051)
- 性质:🔴 红线级(用户可见事件呈现)· 点金-3 交叉审

## 交付范围

- [x] 后端 `GET /api/v1/econ/calendar`(公开只读 · 库字段直出 + 保鲜元信息 · 失败隔离)
- [x] `store.select_calendar`:CST 今天零点起全量(含★1 的 ECB/BOJ/社融——决策卡不
      注入的批次,日历页展示全)· 与决策卡查询口径刻意分离
- [x] 前端 `/calendar`:今天/本周/未来分组 · 地区×重要度筛选 · 星级(3红/2金/1灰)·
      北京时间显式标注 · 时刻待定 · 来源标注 · 空态/错误态 · 免责完整
- [x] 导航:market-switcher「财经日历」Tab(高亮)+ Cmd+K 命令面板项 + sitemap
- [x] ★保鲜可见性:页顶「数据更新时间」= 采集 last-run(非 max(事件ts));
      any_stale →「部分数据更新中」角标
- [x] 🔴 test_econ_calendar_page 四道锁(方向词 rglob 全文件 + 防空锚 / 免责剥注释断言 /
      零 LLM banned 扩至仓内现存 AI 模块 / 字段集钉死)+ i18n 金丝雀
- [x] 对抗自审(4+8 agent 两阶段):6 实锤全修(分组跨午夜 / 导航死点击 / 锁的 4 处假绿,
      每条都构造出绕过路径再修);本地 preview 实测(stub 数据全渲染路径 · 亮/暗 ·
      375px · 筛选/空态/错误态 · 死点击修复双向实点)
- [x] 顺手:P0 DONE.md 验收命令补 https:// 显式标注(Hans 踩过裸域名 0 字节)

## 部署三件套证据(2026-07-10)

1. **Actions 绿**:run 29088502789(merge 3b13565)全 job success
2. **容器真重建**(部署 job 日志 11:16 UTC):`api / worker / web 全 Recreated → Started →
   Healthy`,HEAD reset 对齐 3b13565;无 alembic 变更,日志 0 条 "Running upgrade" 符合预期
3. **真机 curl**(部署后即刻):
   - `GET /api/v1/econ/calendar` → **66 条事件**(seed/rule/fed_json/bea_json 混合),
     `updated_at=08:46 UTC`(= Hans 手动首采时刻,last-run 口径正确),`any_stale=false`
   - ★importance=1 共 21 条(ecb/boj/cn_credit)在列——「决策卡不注入但日历页展示全」达成
   - 头部 5 条时刻逐条对官方吻合:7/15 中国GDP 10:00 CST · 7/20 LPR 09:15 CST ·
     7/23 ECB 14:15 CEST · 7/29 FOMC 14:00 EDT · 7/30 美GDP 08:30 EDT
   - `https://midastrade.asia/calendar` HTTP 200 且 HTML 含「财经日历」;sitemap 含 /calendar

## 已知边界 / P1(详见 ADR 0052)

- 前值/预期/公布值:P0 数据模型无此数据(官方日程源只给日程),不放空列编造;P1 接数值源再上
- en 文案未做(i18n 金丝雀锁着,落地时必须显式扩英文方向词锁)
- PR-B(决策卡局部关联提示)待 Hans 排期

## Hans 验收指引(真机 · Cmd+Shift+R 强刷)

1. 顶部导航应出现「财经日历」Tab(训练营右侧)→ 点进 `/calendar`
2. 首采已跑的话应看到事件列表(7/15 中国GDP ★3、7/23 ECB ★1、7/29 FOMC ★3 等);
   页顶「数据更新:MM-DD HH:mm」应为最近一次采集时间
3. 筛选:点「中国」只剩 LPR/CPI/PPI/GDP/PMI/社融;点「仅重要 ★2+」ECB/BOJ/社融消失;
   「日本」+「仅重要」→ 应显示友好空态
4. Cmd+K 输入「日历」应能跳转
5. 红线抽查:任一事件行绝无 利好/利空/买卖方向 字样——有即红线事故,立刻回报
6. `curl -s https://api.midastrade.asia/api/v1/econ/calendar | jq '.events | length'`
   应 > 0(★命令必须带 https://)
