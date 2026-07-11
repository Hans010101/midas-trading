# 0055 · 欧洲四国经济指标接入(红线级 · 事件数据 + 用户可见呈现)

- 日期:2026-07-11
- 状态:已上线(PR #190)
- 相关:0051-0054(事件层 P0/日历页/韩/日)· docs/research/eu4-econ-calendar-sources.md

## 背景

欧洲桶此前只有 ECB(欧元区货币政策),缺单一国家经济指标。补英/德/法/意四国
CPI/GDP/失业率 + BoE 议息。英国按 Hans 定归欧洲桶(不独立)。走方案①:DSBB 底座 + BoE 种子。

## 决策

### 1. 数据源(零 key · 亲手逆向端点 + 逐日权威对表后写解析器)

- **IMF DSBB `getARCReportList`**(dsbb.imf.org/api/customquery · 逆向其 Angular
  ReportService/CustomQueryService 找到未文档化端点 · Akamai WAF 需浏览器 UA):一个解析器
  覆盖四国 × CPI(CPI00)/GDP(NAG00)/失业率(UEM00)。
- **BoE 议息 2026** 全 8 期年度种子(TLS 指纹墙 curl 不通 → 种子,同 ECB/BOJ/BOK)。

### 2. ★★DSBB 解码(纠正了调研文档的错误 · 本 ADR 核心)

`MonthValues` 是 13 槽定长数组:
- **★发布月 = 槽下标 i(1-12 日历月)**;`Period` 字段 = **数据参考期**(信息用,解析日期
  【不用】)。发布日 = (槽月, 年) + `Day`。年份用 `getAdvanceMonths` 有序月号列表跨年 wrap 推导。
- ⚠️ **调研文档的「Period 月 + Day」解码整体错位一个月**。用 **ONS(英)+ ISTAT(意)权威
  日程逐日对表**发现并纠正:GBR CPI 槽 7/8/9/10 → 2026-07-22/08-19/09-16/10-21 与 ONS
  官方逐日吻合(调研的 07-19/08-16/09-21 全错);GBR GDP=09-30(ONS)、意大利逗号双值
  09-01/09-30(ISTAT)吻合。落地前写 reference decoder 对四组权威数据逐日校验通过。
- `Day` 三形态:普通 "22" / "NLT 25"(不晚于·日不确定) / "1,30"(意大利同槽月双发布,拆分)。
- **DSBB 无时刻** → 存本地 10:00(保 CST 显示日期不跨午夜)+ `time_confirmed=False`
  (不编造时刻,显示「时刻待定」——比硬编造惯例时刻更合红线「无则留空不编造」)。

### 3. 🔴 红线双重焊死(同韩日范式)

四国全部 `importance==1` 且 `markets=["eu"]`(非四交易市场)→ 决策卡永不注入。
`test_eu_events_never_injectable`(DSBB 四国 + BoE 变异)+ DSBB 产物进方向词 grep 语料 +
四国国名/指标名注册表常量进 `test_source_title_constants` 源头锁。

### 4. 保鲜(对抗自审加固)

dsbb 进 FRESH_SOURCES(七源)+ last-run。★**逐国校验**(非聚合):每国 CPI 月度恒有未来
条(保鲜锚)→ 该国 0 条即抛转 stale。对抗自审 P2:旧版聚合 0 守卫会让单国(意大利)SDDS
节点迁移(KOSTAT 2026 改名即先例)被其余三国正常掩盖 → 改逐国抛(monkeypatch 钉死)。
季度品种(GDP/法失业率)靠该国 CPI 保非空,不误报。

### 5. 前端(复用欧洲桶)

gb_*/de_*/fr_*/it_* → `REGION_OF_TYPE`='eu' + `COUNTRY_LABEL_OF_TYPE` 标各自国别
(英/德/法/意 · ECB 保持「欧洲」)+ `SOURCE_LABEL` dsbb · 空态精确提示复用 · 零新组件。

## 自主决策

- DSBB 解码纠错(见 §2,最重要)· 无时刻不编造(time_confirmed=False)· DSBB 单源(CPI 保
  非空免季度误报)· 逐国保鲜校验。

## P1 / P2 待办

- P1:BoE 跨年种子加 2027。
- P2:英 ONS 原生 JSON(18 月前瞻 + 精确时刻 + confirmed/provisional 状态)· 意 ISTAT iCal
  (全指标单 feed + 时刻);德 Destatis iCal + BA 失业 + ifo 种子。法国官方无 feed → 仅 DSBB。
- 排除:Eurostat(欧盟口径 ≠ 本国指标,与目标错配)。
