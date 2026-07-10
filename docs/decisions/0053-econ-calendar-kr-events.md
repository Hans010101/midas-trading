# 0053 · 韩国事件接入 + 日韩合并桶(红线级 · 碰事件数据与用户可见呈现)

- 日期:2026-07-10
- 状态:已上线(PR #188)
- 相关:0051(事件层 P0)· 0052(日历页 PR-A)· docs/research/kr-econ-calendar-sources.md(调研)

## 背景

财经日历已上线 A/中/美/欧/日 事件。Hans 拍板接入韩国(零成本官方源,复用点金-3 调研),
并把「日本」筛选桶升级为「日韩」合并桶(体例同「欧洲」多国合一)。

## 决策

### 1. 数据源(零 key 零注册 · 仿现有 P0 源)

| 事件 | 源 | 模式 |
|---|---|---|
| BOK 议息 ★8 期 | bok.or.kr 官方年表(前一年 10 月末公布) | 年度种子 8 日期 + 10:30:00 KST(RSS 20+ 次实证极严格 · time_confirmed=True) |
| 韩国 CPI/就业/产业活动 各 12 条 | KOSTAT/MODS 官方 xlsx（mods.go.kr/ansk/file/schedule_2026.xlsx） | 每日轮询 · 幂等 upsert · 解析三大月度指标 |

- KOSTAT xlsx **亲手下载解包实测形状**(21KB · 单 sheet · 表头第 3 行 보도일자/보도시간/
  보도자료명/담당과 · 日期 "M.D.(요일)" · 三大指标各 12 条 08:00 KST)后才写解析器(项目铁律)。
- 三大指标韩文子串:소비자물가동향=CPI · 고용동향=就业 · 산업활동동향=产业活动。
- 不接需 key 的源(KOSIS OpenAPI/ECOS 只记录不申请);IMF DSBB 零 key JSON 留作 P1 校验源。
- 12/31「12월 및 연간 소비자물가동향」年度 CPI 例外,解析器按发布日期自然纳入。

### 2. 🔴 韩国红线(写死 · 机器验证)

**韩国事件永不注入决策卡 = 双重焊死**:全部韩国事件 `importance==1` **且**
`markets=["kr"]`(非 cn/us/crypto/hk)。`select_upcoming` 的 min_importance≥2 与
`markets.contains([市场])` 任一条件独立排除韩国。`test_kr_events_never_injectable_into_decision_card`
钉死(变异测试:改 importance→2 或 markets 加 us 锁必红)。

★后果即设计,非缺陷:★1 → 日历页默认态显示、★2+ 筛选下不显示、决策卡不注入韩国。
**绝不因「想让韩国在★2+下显示」提到 2**——提 2 会穿透注入美股/加密决策卡,那是 P1
importance 旋钮本尊(红线级),本 PR 不碰。

其余红线同 P0/PR-A:方向词 grep 全语料 += KOSTAT 解析产物(中英)· 零 LLM(库字段+
静态模板)· 免责完整 · 字段集钉死(韩国不引入任何解读字段)。

### 3. 自主决策:KOSTAT 每日轮询而非「年抓一次」

调研建议「年抓一次」,但改为**每日轮询**(折进 refresh_daily 第 4 源):
- 幂等 upsert,成本 ≈ 1 次 GET;
- 及时捕捉年表改期与 mods.go.kr 改名/404(比年抓一次早发现);
- 统一 3 天保鲜模型——年抓会让「部分数据更新中」徽章永远亮(3 天阈)。
- 失败模式良性:kostat 长期失败时 events_usable(30 天全局硬阈)仍靠 fed/bea/rule_seed 日更为 True,
  韩国存量 30 天内仍展示不丢。
- Hans 可否决改回年抓 + 特殊 stale 阈值。

英文 HTML 兜底:P0 xlsx 现 200 且失败模式已良性 → HTML 硬解析列 P1(路径纯约定的 404
是次年问题,daily 轮询会在 3 天内发现并告警)。

### 4. 前端「日韩」合并桶

- REGION_OF_TYPE 把 boj + bok + kr_* 全映到 `jpkr` 桶(筛选合并);
- ★事件行右侧仍标各自国别(COUNTRY_LABEL_OF_TYPE:boj→日本、bok/kr_*→韩国),用户看得出哪条哪国;
- SOURCE_LABEL += kostat→「韩国国家数据处」;韩国全 ★1 灰星。
- **空态精确提示(方案 A 防困惑)**:某地区本有事件但全 ★1 被「仅重要 ★2+」清空时,给
  「『XX』地区近期事件均为次要(★1),已被『仅重要 ★2+』过滤;关闭该筛选即可查看」;
  其余真空态维持通用提示。

## P1 待办

- 英文 HTML 年表硬解析兜底(次年 mods.go.kr 路径 404 时启用)
- IMF DSBB 月度校验源(零 key,多国可复用)
- BOK GDP(P2,SDDS HTML 年更)
- 2027 KOSTAT/BOK 种子年更(头年 10 月末官方公布后)
