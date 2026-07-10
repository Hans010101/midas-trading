# 0051 · 事件日程提醒层 P0(红线级 · 碰决策卡)

- 日期:2026-07-10
- 状态:已上线(PR #185)
- 相关:docs/research/econ-calendar-selfbuild-feasibility.md(调研)· docs/research/jin10-event-layer-feasibility.md(买线对比,Hans 拍板走自建)

## 背景

决策卡只看技术面,重大宏观事件(FOMC/非农/CPI 等)前后波动放大却无提示。Hans 拍板:
自建零 key 事件日程层,事件**只作「结构体检的风险提示」**呈现,🔴 绝不让模型基于事件给
方向性买卖建议——这是红线级要求,必须机器验证。

## 决策

### 1. 存储:PG 而非 CH(点金-3 交叉审背书 · Hans 可否决)

Hans 口径提过 CH 表,但指定复用的调研 §5.2 结论是 PG:事件是**可变实体**(改期要
UPDATE、按 event_key 幂等 upsert),年增量 ~150 行——CH append 型反而别扭。
`econ_event` 表 + alembic `t1u2v3w4x5y6`,event_key 主键(如 `fomc-2026-07-29`)。

### 2. 数据源(P0 全零 key 零凭证 · 最小事件集不过度扩张)

| 源 | 方式 | 事件 |
|---|---|---|
| Fed calendar.json | 每日拉(BOM=utf-8-sig·标题变体 normalize·两日会取末日·美东时区换算) | FOMC ★3 |
| BEA release_dates.json | 每日拉(ISO 带时区·去重) | 美 GDP ★2 / PCE ★2 |
| 纯规则 | LPR 20日9:15 周末顺延 · 中国 PMI 月末 · 社融 9-15 窗口占位(time_confirmed=False) | ★2/★1 |
| 年度种子(一年一策) | 统计局 2026 官方年表(CPI/PPI/GDP)· ECB 2026H2-2027 · BOJ 2026 | ★1-3 |
| 惯例占位 | 非农第一个周五 8:30 ET(time_confirmed=False·标「以官方为准」) | ★3 |

**BLS 降级(如实)**:官方 2026 年表全部合法通道被 Akamai 403——绝不编造官方日期。
非农用惯例占位;美国 CPI/PPI P0 缺席,P1 走 VPS UA 拉 bls.ics 或 Hans 提供年表补种子。

### 3. ★保鲜口径(写死 · 绝不回退)

事件 ts 在**未来** → **绝不用 max(scheduled_at) 判 stale**(永远假新鲜)。
用「采集任务 last-run 成功时间」(Redis `econ:cal:last_success:{source}`)进 ingest-status:
- 3 天软 stale:仅监控标注,日程照用(失效模式良性——已存的未来日程仍有效)
- 30 天硬阈(`events_usable`):才停决策卡注入,降级为无事件(prompt 零变化)

### 4. 注入设计(零回归)

- `TechnicalSnapshot.econ_events_context` 默认空串:空 = prompt **逐字节零变化**(测试钉死)
- 卡面 `event_risk` = **API 层纯模板派生(零 LLM,红线机器可证)**,`set_cached_card`
  前挂上 → 缓存命中路径自然携带;旧缓存无字段靠默认 None 兼容
- 注入块全 try/except 失败隔离 + `await db.rollback()`(DB 错不污染请求级 session,
  否则静默丢 record_decision 历史行——对抗自审真 PG 复现)
- prompt 改动纯增量:zh `_SYSTEM_BASE` 加一句、en `RED_LINE_PREAMBLE_EN` 加一条,
  既有禁祈使/免责句逐字未动(点金-3 diff 核对)

### 5. 🔴 红线机器验证(tests/services/test_econ_redline.py 四道锁 · CI 硬卡)

1. **方向词 grep**:全语料(规则+种子+两解析器产物,BEA 注册表动态展开)× 两输出面
   (prompt 段 / event_risk)× 中英,零方向词(19 中文 + 6 英文)
2. **免责口径不变**:event_risk 尾带完整「仅供参考,不构成投资建议」(zh)/
   "not investment advice"(en)——ADR0049 精简仅限 x_short,不适用此处
3. **prompt 红线句**:zh + en 全部 4 市场变体均含「事件仅风险背景·绝不给方向」,
   既有不变量(test_prompt_invariants)双保险
4. **spy/never**:monkeypatch 下单入口(place_market_order / process_active_conditionals)
   跑全输出面零调用 + econ_calendar 包源码静态扫描零交易符号 + workflow state 键契约钉死

### 6. worker 工程细节(对抗自审 3 实锤,真 PG 复现后修)

- 三源共享 session 时 except **必须 rollback**,否则源1 DB 层失败把 session 打进
  aborted 态、源2/3 连坐(违背单源隔离);照 perp_cross_liquidation 既有范式
- `upsert_events` 批内按 event_key 去重(后者胜):同 key 两行进同一条
  INSERT..ON CONFLICT = CardinalityViolation(上游日历实测出过重复日期)
- celery `timezone="Asia/Shanghai"` 下 crontab 数字是 **CN 本地**:beat 每日 09:07 CST

## P1 待办

- BLS 官方年表双保险(VPS UA 拉 bls.ics / Hans 浏览器提供年表)→ 非农确认日期 + 美国 CPI/PPI 种子
- `parse_fed_events` 跨月两日会守卫(days="30-1" 型,9 年数据零出现,纯理论)
- ECB/BOJ/社融 importance=1 + min_importance=2 → 存库但不注入决策卡(P0 保守有意为之);
  想放开只改 `select_upcoming` 的 min_importance 一处(产品旋钮,Hans 拍)
- LPR 法定节假日表(2026H2 逐月核过仅周末顺延,无假期冲突)
