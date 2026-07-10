# 韩国事件接入 · 交付归档(DONE)

- 日期:2026-07-10
- PR:#188 · 决策:docs/decisions/0053 · 调研:docs/research/kr-econ-calendar-sources.md
- 性质:🔴 红线级(碰事件数据 + 用户可见呈现)· 点金-3 交叉审

## 交付范围

- [x] BOK 议息年度种子(2026 全 8 期 · 10:30:00 KST · importance=1 · markets=["kr"])
- [x] KOSTAT/MODS 官方 xlsx 年表源:parse_kostat_rows(纯函数 · 三大月度指标 CPI/就业/
      产业活动各 12 条)+ fetch_kostat_events(当年主 · 次年 best-effort)· openpyxl 复用
- [x] worker 第 4 源接入 refresh_daily(每日轮询 · 失败隔离 + rollback)· FRESH_SOURCES += kostat
- [x] 🔴 韩国不注入决策卡双重焊死(importance=1 + markets=["kr"])· test 变异钉死
- [x] 前端「日本」桶→「日韩」合并桶(单条仍标各自国别)+ KOSTAT 来源标注 + ★2+ 空态精确提示
- [x] 红线机器验证:方向词 grep 语料 += KOSTAT 产物 · 页面四道锁自动覆盖韩国文案 · 特性钉

## 部署三件套证据(2026-07-10)

1. **Actions 绿**:run 29103250430(merge e911e79)全 job success
2. **容器真重建**(部署 job 日志 15:29 UTC):`api / worker / web 全 Recreated`,api Healthy;
   HEAD 对齐 e911e79;无 alembic 变更(0 条 "Running upgrade",复用 econ_event 表)
3. **真机 curl**(部署后即刻):
   - `GET /api/v1/econ/calendar` → `sources` 现为 **4 源**(fed_json/bea_json/**kostat**/rule_seed)
     = 新代码上线;线上 `ingest-status.econ_jobs` 含新 kostat 源
   - kostat `last_success=null, stale=True` 符合预期:08:46 UTC 那轮采集跑的是旧 3 源代码
     (早于本次 15:29 部署),新的 BOK 种子 + KOSTAT 源尚未刷入

**⏳ 待首次采集**:韩国事件(BOK 种子 + KOSTAT)在下一次 `refresh_daily` 刷入。
下一次自动 beat = 09:07 CST(01:07 UTC 次日)。Hans 可服务器一条命令立即触发:
`docker exec midas-worker celery -A celery_app call tasks.econ_calendar.refresh_daily`
触发后:
- `curl -s "https://api.midastrade.asia/api/v1/econ/calendar" | jq '[.events[]|select(.event_type|test("bok|kr_"))]|length'`
  应 > 0(★命令带 https://);`.sources` 里 kostat.stale 应转 false
- 日历页 `/calendar`「日韩」桶应同出日本 + 韩国;决策卡侧(美股/加密/A股/港股)**绝不**含韩国

## Hans 验收指引(真机 · Cmd+Shift+R)

1. `/calendar` 筛选行「日本」应变「日韩」;点它同出日本 BOJ + 韩国 BOK/CPI/就业/产业活动,
   每条右侧标各自国别(日本/韩国)
2. 韩国事件全为灰 ★1;点「仅重要 ★2+」→ 日韩(及欧洲)应显精确空态提示(非无差别空态)
3. 红线抽查:任一韩国事件行绝无 利好/利空/买卖方向 字样——有即红线事故,立刻回报
4. 决策卡侧:美股/加密/A股/港股 决策卡**绝不**出现韩国事件(韩国 importance=1+markets=["kr"]
   双重焊死不注入)
5. `curl -s "https://api.midastrade.asia/api/v1/econ/calendar" | jq '[.events[]|select(.event_type|test("bok|kr_"))]|length'`
   应 > 0(★命令必须带 https://);`.sources` 应含 kostat

## 已知边界 / P1(详见 ADR 0053)

- 英文 HTML 兜底 P1(xlsx 现 200,失败模式良性)· IMF DSBB 校验源 P1 · BOK GDP P2
- 2027 KOSTAT/BOK 种子年更(头年 10 月末官方公布后)
