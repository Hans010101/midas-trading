# 日本经济指标接入 · 交付归档(DONE)

- 日期:2026-07-11
- PR:#189 · 决策:docs/decisions/0054 · 上一刀:韩国(#188 · ADR0053)
- 性质:🔴 红线级(事件数据 + 用户可见呈现)· 点金-3 交叉审

## 交付范围

- [x] 統計局 e-Stat XML 解析(★UTF-16):日本CPI(全国月度)+ 日本失业率(基本集計)
- [x] BOJ tkohyos.xlsx 解析:日本短观 Tankan 概要速報(时刻行/日期行配对)
- [x] 两源进 refresh_daily(六源)+ FRESH_SOURCES(jp_estat/boj_xlsx)+ last-run 保鲜 + rollback 隔离
- [x] 🔴 红线双重焊死:日本全 importance=1 + markets=["jp"] → 决策卡永不注入
      (test_jp_events_never_injectable + 方向词语料含日本产物 · 变异可证)
- [x] 前端 jpkr 桶复用:jp_cpi/jp_unemp/jp_tankan → 日韩桶 + 单条标「日本」+ 統計局/BOJ 来源标注
- [x] 抓取型自动滚动(翻年自动补,不需改码);过期显示保持现状不碰
- [x] 对抗自审(4+N agent):见下

## 部署三件套证据(2026-07-11)

1. **Actions 绿**:run 29136497299(merge 9c975c6)全 job success
2. **容器真重建**(部署 job 日志 02:38 UTC):`api / worker / web 全 Recreated`,api Healthy;
   HEAD 对齐 9c975c6;无 alembic 变更(0 条 "Running upgrade",复用 econ_event 表)
3. **真机 curl**(部署后即刻):
   - `GET /api/v1/econ/calendar` → `sources` 现为 **6 源**(fed_json/bea_json/kostat/
     **jp_estat**/**boj_xlsx**/rule_seed)= 新代码上线
   - 日本经济指标事件 = 0 条(worker 未跑新代码前预期:上次采集早于本次 02:38 部署)

**⏳ 待首次采集**:日本事件(統計局 CPI/失业率 + BOJ 短観)在下一次 `refresh_daily` 刷入。
Hans 可服务器一条命令立即触发:
`docker exec midas-worker celery -A celery_app call tasks.econ_calendar.refresh_daily`
触发后:
- `curl -s "https://api.midastrade.asia/api/v1/econ/calendar" | jq '[.events[]|select(.event_type|startswith("jp_"))]|length'`
  应 > 0(★命令带 https://);`.sources` 里 jp_estat/boj_xlsx.stale 应转 false
- 日历页「日韩」桶应同出 日本(CPI/失业率/短観/BOJ议息)+ 韩国,单条标各自国别

## 已知边界 / P1·P2(详见 ADR 0054)

- P2:内阁府 GDP(QE)/景気動向 HTML-only(需令和转换,同韩国 GDP 档)
- P1:統計局英文兜底;IMF DSBB 多国校验源(已核实零 key 可用,生产不接)

## Hans 验收指引(真机 · Cmd+Shift+R 强刷)

日本事件在下次 `refresh_daily` 刷入。触发首采(否则等 09:07 CST beat):
`docker exec midas-worker celery -A celery_app call tasks.econ_calendar.refresh_daily`
触发后:
- `/calendar`「日韩」桶应同出 日本(CPI/失业率/短観/BOJ议息)+ 韩国,单条标各自国别
- `curl -s "https://api.midastrade.asia/api/v1/econ/calendar" | jq '[.events[]|select(.event_type|startswith("jp_"))]|length'`
  应 > 0(★带 https://);`.sources` 里 jp_estat/boj_xlsx.stale 应转 false
- 决策卡侧(美股/加密/A股/港股)**绝不**含日本经济指标;任一日本行无利好利空/买卖方向词
