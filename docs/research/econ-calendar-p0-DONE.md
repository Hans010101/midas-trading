# 事件日程提醒层 P0 · 交付归档(DONE)

- 日期:2026-07-10
- PR:#185(2 主 commit + 2 修复/补强 commit)· 决策:docs/decisions/0051
- 性质:🔴 红线级(碰 LangGraph 决策卡 prompt)· 已走点金-3 交叉审(放行 + 2 补强已落)

## 交付范围(P0 全部完成)

- [x] `econ_event` PG 表 + alembic 迁移(t1u2v3w4x5y6)· event_key 幂等 upsert
- [x] `services/econ_calendar/`:fetchers(Fed/BEA 零 key)+ rules(LPR/PMI/社融窗口/非农占位)
      + 年度种子(统计局 2026/ECB/BOJ)+ store + format(纯模板)
- [x] worker `tasks.econ_calendar.refresh_daily` · beat 每日 09:07 CST · 三源隔离(rollback 修复)
- [x] 决策卡注入:prompt「未来7天重大事件」段(空=逐字节零变化)+ 卡面 event_risk
      (API 层纯模板零 LLM · 随卡入缓存)
- [x] ingest-status 加 econ_jobs(last-run 保鲜口径 · 3 天软 stale / 30 天硬阈)
- [x] 前端双卡组件(AiDecisionCard + CryptoAiCard)渲染 📅 事件提示行
- [x] 🔴 红线机器验证 test_econ_redline 四道锁(方向词 grep / 免责 / prompt 句 / spy-never)
- [x] 点金-3 交叉审:✅ 放行;「修后合并」2 项测试补强 + P1-2 warn 已落
- [x] 对抗自审(4 维度 8 agent):3 实锤(session 污染连坐 / beat 时区 / 请求 session 污染)
      全部真 PG 复现后修复;1 误报驳回

## 部署三件套证据(2026-07-10)

1. **Actions 绿**:run 29073822617(merge 4b3c30c)四 job 全 success(web/api/worker build+push + SSH 部署)
2. **容器真重建 + 迁移日志**(Actions 部署 job 日志,06:34 UTC):
   - `Running upgrade s0t1u2v3w4x5 -> t1u2v3w4x5y6, 建 econ_event 表(事件日程提醒层 P0)`
   - `midas-api Recreated → Started → Healthy` · `midas-worker Recreated → Started` · web 同
   - 服务器 HEAD reset 对齐 4b3c30c(github.sha 派生,非盲取 origin/main)
3. **真机 curl**(部署后即刻):
   - `GET /api/v1/crypto/ingest-status` → `econ_jobs` 三源(fed_json/bea_json/rule_seed)
     已在响应中,首跑前 `last_success=null, stale=true` 符合预期
   - 线上 OpenAPI `DecisionCardResponse.event_risk` 字段存在

**⏳ 待首次采集**:worker 重建(14:34 CST)错过当日 09:07 CST beat,首次自动刷新=
次日 09:07 CST。Hans 可服务器一条命令立即触发:
`docker exec midas-worker celery -A celery_app call tasks.econ_calendar.refresh_daily`
触发后重跑验收 curl(★注意必须带 https://,裸域名 curl 会拿到 0 字节):
`curl -s https://api.midastrade.asia/api/v1/crypto/ingest-status | jq .econ_jobs`
三源应变 `stale=false`;再按下方验收指引查决策卡。

## 已知降级 / P1(详见 ADR 0051 § P1)

- BLS 被 Akamai 403:非农=惯例占位「以官方为准」;美国 CPI/PPI P0 缺席
- ECB/BOJ/社融存库但 importance<2 不注入(P0 保守·产品旋钮待 Hans)
- Fed 跨月两日会守卫 / LPR 节假日表(纯理论加固)

## Hans 验收指引(真机)

1. `curl -s https://api.midastrade.asia/api/v1/crypto/ingest-status | jq .econ_jobs`
   → 应见 fed_json / bea_json / rule_seed 三源 last_success + stale=false
2. 任一市场详情页刷新决策卡(避开 1h 缓存:换个没看过的标的),若未来 7 天窗内有
   ★2+ 事件(下一个:7/15 中国 GDP 发布会 · 7/23 ECB 不到 ★2 不显 · 7/29 FOMC),
   卡面应出现「📅 近期重大事件…仅供参考,不构成投资建议」提示行;crypto-preview 同查
3. 事件提示行绝无买/卖/方向词——有即红线事故,立刻回报
