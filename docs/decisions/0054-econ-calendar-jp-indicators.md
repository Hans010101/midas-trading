# 0054 · 日本经济指标接入(红线级 · 事件数据 + 用户可见呈现)

- 日期:2026-07-11
- 状态:已上线(PR #189)
- 相关:0051(P0)· 0052(日历页)· 0053(韩国)· docs/research/jp-econ-calendar-sources.md

## 背景

日本此前只接 BOJ 议息(4 条,rules.py 年度种子),缺经济指标(CPI/失业率/短観)——
韩国 KOSTAT 的对等物缺失。调研盘点出两个零 key 官方机读源,本 PR 接入,归入 #188 已建
的「日韩」合并桶。

## 决策

### 1. 数据源(全零 key 官方机读 · 亲手下载解包实测形状后写解析器)

| 事件 | 源 | event_type | 要点 |
|---|---|---|---|
| 日本CPI | 統計局 e-stat_cpi.xml | jp_cpi | 全国月度 08:30 |
| 日本失业率 | 統計局 e-stat_roudou.xml | jp_unemp | 基本集計 08:30 |
| 日本短观Tankan | BOJ tkohyos.xlsx | jp_tankan | 概要速報 08:50 · 季度 |

- **★★UTF-16 编码坑**:統計局 XML 是 UTF-16 LE(BOM `fffe`)。`resp.text` / `decode("utf-8")`
  会误解成乱码 → 必须 `content.decode("utf-16")`;且 ElementTree 拒带 encoding 声明的
  str(部分 Python 版本 ValueError)→ 解码后先 `re.sub` 去掉 `<?xml … ?>` 声明再 `fromstring`。
- **keep 谓词**(排除非头条发布):CPI 只取 `class_1=="全国" and class_2.endswith("月分")`
  (排除東京都区部中旬速報、2025年基準遡及/接続指数);失业率只取 `class_2.startswith("基本集計")`
  (排除詳細集計 14:00)。同日多 class_5 → 按日期去重取首见(08:30 头条)。
- **os_code name 校验**:parse_estat_xml 校验 `<os_code name>` == 期望统计名,不符即返回 []
  + warning(防 e-Stat 换文件/路径漂移导致静默误采别的统计)。
- **BOJ 矩阵**:「統計データ」sheet 是 统计×月矩阵,每统计两行(时刻行 col3="08:50:00" +
  日期行 col3="(四半期)"·月列原生 datetime,无需令和转换)· 同 col1 名配对取时刻;短観只采
  「概要」(排除調査全容/時系列 次日补充)。

### 2. ★抓取型自动滚动(补日本的额外价值)

两源都是滚动 9-12 个月未来的机读源 → 官方页面翻年时每日 refresh_daily 自动采集自动补,
**不需像年度种子那样跨年改代码**(接日本经济指标反而减少手动残留)。进 FRESH_SOURCES
(jp_estat / boj_xlsx · 六源)+ last-run 保鲜(★非 max(事件ts))+ 每源 rollback 隔离 + 0 条
warn。失效模式良性:源断 30 天内存量仍有效只标注不丢。

### 3. 🔴 红线双重焊死(同韩国范式)

日本全部事件 `importance==1` **且** `markets=["jp"]`(非四交易市场)→ `select_upcoming` 的
min_importance≥2 与 markets.contains 任一独立排除,**决策卡永不注入日本**。
`test_jp_events_never_injectable_into_decision_card` + 日本三指标解析产物进方向词 grep 语料;
改坏 importance→2 / markets→us / 标题注入方向词 → 锁必红(变异可证)。
★绝不为了让日本在★2+显示提星(穿透注入=importance 旋钮本尊·红线级·本 PR 不碰)。

### 4. 前端(最小改动 · 复用 #188 日韩桶)

jp_cpi/jp_unemp/jp_tankan 加进 `REGION_OF_TYPE`→jpkr + `COUNTRY_LABEL_OF_TYPE`→「日本」
(单条标各自国别)+ `SOURCE_LABEL`(統計局/BOJ)· 空态精确提示、过期双层过滤全复用,零新组件。

## 自主决策

- **源粒度 = 2 个 FRESH_SOURCES**:jp_estat(統計局 CPI+失業率两 XML,同发布方,fetch 内每
  XML 独立隔离,全挂才抛→转 stale,部分成功返回已得)+ boj_xlsx。统計局是同一发布系统,一个
  新鲜度信号即够。
- **只做 3 头条指标**,不扩張。短観只采概要速報。

## P1 / P2 待办

- P2:内阁府 GDP(QE)+ 景気動向指数(HTML-only,需令和转换,同韩国 GDP 档)。
- P1:統計局英文兜底;IMF DSBB 多国校验源(可选,已核实零 key 可用,生产不接)。
- 全局 P2:0 条仍 mark_success(同 fed/bea/kostat 口径,留全局统一)。
