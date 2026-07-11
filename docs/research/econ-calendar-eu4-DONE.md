# 欧洲四国经济指标接入 · 交付归档(DONE)

- 日期:2026-07-11
- PR:#190 · 决策:docs/decisions/0055 · 上一刀:日本(#189 · ADR0054)
- 性质:🔴 红线级(事件数据 + 用户可见呈现)· 点金-3 交叉审

## 交付范围

- [x] IMF DSBB(逆向未文档化端点 · WAF 浏览器 UA)四国×CPI/GDP/失业率一个解析器
- [x] ★DSBB 解码纠错:槽下标=发布月(非 Period)· ONS+ISTAT 权威逐日对表验证
- [x] Day 三形态(普通/NLT/逗号双值)· 跨年 wrap · 无时刻 time_confirmed=False
- [x] BoE 议息 2026 全 8 期年度种子(恒周四 12:00 London)
- [x] 🔴 红线双重焊死:四国全 importance=1 + markets=["eu"] → 决策卡永不注入
      (test_eu_events_never_injectable + 源头锁 + 方向词语料 · 变异可证)
- [x] dsbb 进 refresh_daily(七源)+ ★逐国保鲜校验(单国掉线即抛转 stale)
- [x] 前端 gb_*/de_*/fr_*/it_* 归欧洲桶 + 单条标国别 + dsbb 来源标注
- [x] 对抗自审(4+N agent):1 P2(单国掩盖漂移)已修

## 部署三件套证据(2026-07-11)

1. **Actions 绿**:run 29140474559(merge 4a9d921)全 job success
2. **容器真重建**(部署 job 日志 05:06 UTC):`api / worker / web 全 Recreated`,api Healthy;
   HEAD 对齐 4a9d921;无 alembic 变更(0 条 "Running upgrade",复用 econ_event 表)
3. **真机 curl**(部署后即刻):
   - `GET /api/v1/econ/calendar` → `sources` 现为 **7 源**(fed_json/bea_json/kostat/jp_estat/
     boj_xlsx/**dsbb**/rule_seed)= 新代码上线
   - 欧洲四国事件 = 0 条(worker 未跑新代码前预期:上次采集早于本次 05:06 部署)

**⏳ 待首次采集**:欧洲事件(DSBB 四国 + BoE 种子)在下一次 `refresh_daily` 刷入。
Hans 可服务器一条命令立即触发:
`docker exec midas-worker celery -A celery_app call tasks.econ_calendar.refresh_daily`
触发后按下方验收指引;★重点抽查英国 CPI/GDP 日期与 ONS 官网一致(DSBB 解码已逐日对表纠正)。

## 已知边界 / P1·P2(详见 ADR 0055)

- P1:BoE 跨年种子加 2027
- P2:英 ONS 原生(18 月前瞻)· 意 ISTAT iCal · 德 Destatis/ifo;法国仅 DSBB
- 排除:Eurostat(欧盟口径≠本国指标)

## Hans 验收指引(真机 · Cmd+Shift+R 强刷)

欧洲事件在下次 `refresh_daily` 刷入。触发首采:
`docker exec midas-worker celery -A celery_app call tasks.econ_calendar.refresh_daily`
触发后:
- `/calendar`「欧洲」桶应同出 英/德/法/意(CPI/GDP/失业率)+ ECB + BoE,单条标各自国别;
  DSBB 事件显示「时刻待定」
- `curl -s "https://api.midastrade.asia/api/v1/econ/calendar" | jq '[.events[]|select(.event_type|test("^(gb|de|fr|it)_"))]|length'`
  应 > 0(★带 https://);`.sources` 里 dsbb.stale 应转 false
- ★抽查英国 CPI/GDP 日期与 ONS 官网一致(我已逐日对表,真机复核更稳);决策卡侧
  (美股/加密/A股/港股)**绝不**含欧洲经济指标;任一行无利好利空/买卖方向词
