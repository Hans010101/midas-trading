# 0052 · 财经日历页 PR-A(红线级 · 用户可见事件呈现)

- 日期:2026-07-10
- 状态:已上线(PR #186)
- 相关:0051(事件日程层 P0)· docs/research/econ-calendar-p0-DONE.md

## 背景

P0 把事件日程接进了决策卡(局部风险提示)。Hans 拍板加「全局入口」:导航栏独立
「财经日历」页,把 P0 存量**全部**事件对用户展示——包括决策卡保守不注入的
importance=1 批次(ECB/BOJ/社融窗口)。纯展示,不扩源、不加 LLM 解读。

## 决策

### 1. 展示口径与决策卡口径刻意分离

`store.select_calendar`(CST 今天零点起全量 · 含★1 · 升序 limit 500)与决策卡
`select_upcoming`(7 天窗 · ≥★2 · limit 5)是两个独立查询——日历页是用户主动查,
展示全;决策卡是被动注入,保守。互不影响,P0 红线锁(test_econ_redline)原样全绿。

### 2. 🔴 红线(test_econ_calendar_page 四道锁 · CI 硬卡)

页面只呈现客观事实:时间(北京时间显式 Asia/Shanghai)/事件名/地区/星级/来源。
1. 方向词 grep:日历前端文件目录级 rglob(拆组件不逃逸)+ 防空 glob 锚 + 两处导航
   入口;中文全文 + 英文分级(buy/sell/bullish/bearish 任意字面量 \b;long/short 限
   含中文文案串,放行 Intl 合法值)+ i18n 金丝雀(next-intl 落地必须显式扩锁)
2. 免责完整「仅供参考,不构成投资建议」——★剥注释后断言(头注释含免责字样会喂饱
   原始源码断言=死断言,对抗自审变异实测出的坑)
3. 零 LLM 渲染路径:前端剥注释后 banned 扫描(覆盖仓内现存 AI 面模块:ai-card/
   api/chan/strategy/analysis——旧六词对 import CryptoAiCard 零命中=假绿,已扩);
   后端 /econ/calendar 路由零 services.ai/llm 符号
4. EconEventOut 字段集钉死=纯客观事实字段,加「解读/方向」字段必先过闸

### 3. 关键取舍

- **前值/预期/公布值不放列**:P0 数据模型没有(官方日程源只给日程不给值,本 PR 禁
  扩源)。Hans 口径「有则显示无则留空不编造」→ 无字段=不放空列,字段集测试钉死;
  P1 接了数值源再上列。
- **地区筛选按 event_type 归属**(cn/us/eu/jp),不用 markets 字段(那是决策卡影响面
  口径:ECB 的 markets=["us"]);「加密相关」= markets 含 crypto。
- **保鲜可见性**:页顶「数据更新时间」= 各源 last-run 最新者(绝非 max(事件ts));
  any_stale → 不打扰的「部分数据更新中」角标;redis 挂了日程照发(失败隔离)。
- **跨午夜自愈**:d<today 的陈旧缓存事件丢弃(绝不顶「今天」标题);query
  refetchInterval 15min(全局关了 refetchOnWindowFocus,长开页签否则永久冻结)。

### 4. 导航死点击顺手修(共享组件 · 既有缺陷)

中性页(/calendar /watchlist /lab /academy /account…)点「A股/美股」Tab 原本落到
`setMarket` 兜底=死点击(页面零反应 + 静默持久化改写 workbench 市场与默认标的)。
修:workbench 显式分支保留原行为(零回归 · preview 实点验证),中性页跳对应市场
首页(与 crypto/hk 行为对齐)。

## P1 待办

- 前值/预期/公布值(需数值源,P1 评估)
- en 文案(i18n 金丝雀会逼停,届时扩英文锁)
- 事件详情/提醒订阅(PR-B 决策卡局部关联提示是下一刀,Hans 排期)
