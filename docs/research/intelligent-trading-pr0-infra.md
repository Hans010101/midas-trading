# 智能交易第一期 · PR-0 基础设施调研

> 纯调研产出。回答三问:`scan_signals`/`compute_atr` 怎么调、复用托管哪些、信号快照怎么存。
> 为 PR-1~6 铺路。**未碰任何业务代码**(仅本文档)。证据均带 `file:line`。

## 0. 结论速览

| 问题 | 结论 |
|---|---|
| 技术信号怎么算 | `scan_signals(klines, strategy)` 5 个纯 K线扫描器(一次一个)+ `scan_extreme(...)` 单独调 · ★**无"一次算6个"的函数,PR-1 自己包装** |
| 极端信号标量从哪来 | CH 三表(`select_funding_rates`/`select_open_interest`/`select_long_short`)· 取数逻辑 `_scan_extreme_for` 现在**埋在端点层**(analysis.py:414)→ ★PR-1 需提取成 service 函数 |
| ATR 怎么算 | `compute_atr(klines, period=14)`(indicators.py:156)· 现成 · `trading_plan.py` 已用它做止损 |
| 复用托管 | **完整照搬** managed 8 文件架构 → 改名 managed→intelligent · 红线照旧(唯一入口/引擎零碰/独立模块过守卫) |
| 信号快照怎么存 | 仿 `boll_scan`:async task + `asyncio.run` + `redis.set(key, json, ex=TTL)` · 新 key `intelligent:signals:latest` |

---

## 1. 技术信号:scan_signals + compute_atr 怎么调(实测签名)

### scan_signals(strategy_signals.py:473)
```python
def scan_signals(klines: list[Kline], strategy: StrategyKind) -> list[StrategySignal]
#   strategy ∈ {"ma_cross","rsi_reversal","boll_reversion","macd_cross","kdj_cross"}
#   返回 ts 升序信号点序列 · 取 [-1] 是最新信号 · 空=无信号
```
- ★**一次只算一个 strategy**(按 `_SCANNERS` dict 分发 strategy_signals.py:464)· 要 6 个就调 6 次
- 5 个扫描器**纯 K线驱动**,无额外标量 · 各默认参数:ma(5/20)·rsi(14/30/70)·boll(20/2.0)·macd(12/26/9)·kdj(9/3/3)
- `StrategySignal`(schema/strategy.py:33):`ts/price/kind("buy"|"sell")/reason/levels{}/strength`

### scan_extreme(strategy_signals.py:385)— ★不入 _SCANNERS,要单独调
```python
def scan_extreme(klines, *, funding_rate: float|None, oi_usd_series: list[float]|None,
                 long_short_ratio: float|None) -> list[StrategySignal]
#   仅 crypto perp · 三者任一极端即触发 · 某项 None = 优雅降级不参与
#   阈值:|funding|>0.0005 · 近12根OI变动≥±10% · 多空比>2.0或<0.5
```

### compute_atr(indicators.py:156)
```python
def compute_atr(klines: list[Kline], period: int = 14) -> float  # Wilder 平滑 · 不足返 0.0
```

### 最小数据输入(每币)
- **K线:≥26 根 15m**(macd 预热最苛刻)· 实取 50 根冗余 · `select_kline(symbol, market="crypto", period="15m", limit=50, instrument="perp")`(clickhouse_client.py:226)
- **extreme 三标量**(仅 perp):见下

---

## 1·B. ★指标 → 方向分(PR-3 打分引擎核心 · 本轮调研关键)

★**关键认知**:`scan_signals` 返回的是【信号事件序列】(何时金叉/穿轨那一根),**不是"当前方向状态"**。多指标共振打分要的是"每个指标当前偏多/偏空",所以**不用 `scan_signals` 的信号点**,而用 `indicators.compute_*`(返回最新一根的指标当前值)判方向:

| 指标 | 权重(Hans 定) | 方向分来源(当前值) | 偏多 +1 | 偏空 −1 |
|---|---|---|---|---|
| 布林 | **2.0** | `boll:snapshot:latest` 的 `bias`(现成·托管在吃·无需重算) | bias=偏多 | bias=偏空 |
| MACD | **1.5** | `compute_macd(klines)`(indicators.py:58)→ DIF vs DEA | DIF>DEA | DIF<DEA |
| MA | **1.5** | `compute_ma(klines)`(indicators.py:48)→ MA5 vs MA20 | MA5>MA20 | MA5<MA20 |
| RSI | **1.0** | `compute_rsi(klines)`(indicators.py:87)→ RSI vs 50 | RSI>50 | RSI<50 |
| KDJ | **1.0** | `compute_kdj(klines)`(indicators.py:117)→ K vs D | K>D | K<D |
| perp 极端 | **1.0** | `scan_extreme(...)` → kind(★反向情绪:正费率高=多头拥挤→偏空) | kind=buy | kind=sell |

→ **加权求和 → > +3.0 开多 / < −3.0 开空 / 中间不动**(满足 Hans 策略)。
满分(全偏多)= 2.0+1.5+1.5+1.0+1.0+1.0 = **8.0**;±3.0 阈值 ≈ 需布林 + 1~2 个指标同向共振。

★**为什么用 compute_\* 不用 scan_signals**:scan_signals 是"事件"(金叉那一根),大部分时候 `[-1]` 很旧或为空,**共振打分需要"每根都有的持续方向"**。`compute_*` 返回当前值,每根都有方向,正适合打分。`scan_signals` 的信号点 + `current_triggered`(analysis.py:498)更适合"事件触发"语义,本模块用不上。

★**中性带建议**(PR-3 定):可给每指标设中性区(RSI 45~55=0 · MA5≈MA20 一定阈值内=0),避免噪声反复开平。

★**extreme 方向口径已确认**(strategy_signals.py:385 docstring):反向情绪 —— 资金费率正高=多头拥挤→**偏空**;多空比>2=过度做多→**偏空**;OI 急变=情绪转折(随 funding/多空比方向或逆价格)。

---

## 2. 极端信号标量来源(★PR-1 关键)

`_scan_extreme_for`(analysis.py:414)现在**埋在 API 端点层**,逻辑:仅 crypto perp,三处独立 try 取数(任一失败→None 降级):

| 标量 | CH 查询函数 | 文件 | 取值 |
|---|---|---|---|
| 资金费率 | `select_funding_rates(client, sym, limit=1)` | clickhouse_crypto.py:114 | `fr[-1].rate` |
| OI 序列 | `select_open_interest(client, sym, limit=20)` | clickhouse_crypto.py:151 | `[o.oi_usd for o in oi]` |
| 多空比 | `select_long_short(client, sym, limit=1)` | clickhouse_crypto.py:193 | `ls[-1].top_account_ratio` |

→ ★**PR-1 必做**:把 `_scan_extreme_for` 从端点提取成 service 工具函数(如 `services/ai/extreme_signals.py`),端点 + PR-1 worker 都调(DRY)。这是 PR-1 唯一要碰的"现有代码"(端点改调新函数,行为不变)。

---

## 3. 复用托管交易(仿 managed → intelligent)

完整照搬 managed 8 文件架构,改名 managed→intelligent(Redis key / 列名 / 端点前缀 / task name):

| 现有(managed) | 新建(intelligent) | PR |
|---|---|---|
| `services/virtual_trading/managed/account.py`(ensure_managed_account/系统用户+10万U钱包) | `intelligent/account.py` | PR-2 |
| `managed/guard.py`(开关+仓位约束+三平仓开关+tp_pct) | `intelligent/guard.py` | PR-2 |
| `managed/open.py`(run_managed_open→route_open_perp+标记) | `intelligent/open.py` | PR-4 |
| `managed/close.py`(run_managed_close→route_close_perp+_exit_reason) | `intelligent/close.py` | PR-5 |
| `managed/stats.py`(compute_managed_stats) | `intelligent/stats.py` | PR-6 |
| `api/v1/managed_admin.py`(独立模块·AdminDep·8端点) | `api/v1/intelligent_admin.py` | PR-6 |
| `worker/tasks/managed_trading.py`(open/close beat) | `worker/tasks/intelligent_trading.py` | PR-4/5 |
| `web/app/admin/managed/page.tsx` + `lib/api/managed.ts` | `admin/intelligent/` | PR-6 |

### 红线(照旧·必守)
- 🔴 **唯一入口**:开/平仓只调 `route_open_perp`/`route_close_perp`(perp_dispatcher)· 不重写撮合 · 引擎三文件零碰
- 🔴 **post-open 标记**:`pos.intelligent=True`(靠 order.position_id · 引擎默认 False)
- 🔴 **独立模块过架构守卫**:`intelligent_admin.py` 不在 admin.py import(守卫 test_admin_domain_no_engine_no_login_import 递归扫 admin 域禁 virtual_trading)· 直接在 `api/v1/__init__.py` 注册 · 加同款 intelligent 守卫测
- 🔴 **per-币 commit 隔离** · **平仓不被开关 OFF 拦**(已有仓必须监控)
- 🔴 **系统用户不可登录**(password_hash=None+google_sub=None)

---

## 4. ★关键差异:intelligent ≠ managed(不是简单照搬)

| 维度 | managed(托管·做T前向测试) | intelligent(智能交易) |
|---|---|---|
| **选币/开仓** | boll 偏多∩transition → 只做多 | ★PR-3 打分共振引擎(布林+信号快照打分 → ±3.0阈值)→ **做多 AND 做空** |
| **side** | 只 LONG | ★LONG + **SHORT**(route_open_perp side=SHORT) |
| **退出** | TP%(盈利%)/信号(≠偏多)/超时24h | ★ATR 止损价 / 止盈 2:1 / 信号反转(close.py 退出逻辑要改) |
| **止损** | 无(只 TP%) | ★compute_atr → 止损价(开仓时算 + 平仓监控) |
| **强平** | ★禁强平(`managed.is_(False)` perp_cross_liquidation.py:90) | ★**不禁强平** → intelligent 仓 `managed=False` **自然进强平扫描**(Hans 要"强平兜底·ATR止损先触发")→ **PR-2/5 不用碰强平 worker** |
| **信号源** | 只读 `boll:snapshot:latest` | 读 `boll:snapshot:latest` + ★新 `intelligent:signals:latest`(PR-1 建) |
| **开仓信号记录** | 无 | ★记录哪些指标共振(PR-4·为 PR-7 复盘+看板) |

### 迁移(PR-2)
`VirtualPerpPosition` 加两列(nullable·仿 managed 范式 perp.py:153)· `last_bias` 已有可复用:
```python
intelligent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
intelligent_close_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
# (可能还要:开仓信号快照 JSON 列 · 或单独表记录共振指标 · PR-4 定)
```

---

## 5. 信号快照存储范式(PR-1:intelligent:signals:latest)

仿 `boll_scan`(worker/tasks/boll_scan.py):

```python
@shared_task(name="tasks.crypto.intelligent_signals_scan", max_retries=0)
def intelligent_signals_scan() -> dict:           # ★Celery task 同步入口
    return asyncio.run(_scan_async())             # asyncio.run 包 async(boll_scan.py:233)

async def _scan_async():
    redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)  # ★str 不是 bytes
    ch = await ClickHouseClient.create()
    universe = (await _all_usdt_perp_symbols(ch._client))[:150]   # 150 币(crypto_metrics_ingest)
    rows = []
    for sym in universe:
        klines = await ch.select_kline(symbol=sym, market="crypto", period="15m",
                                       limit=50, instrument="perp")
        if len(klines) < 26: continue
        # ★方向分用 indicators.compute_*(当前值 · 见 §1·B),不是 scan_signals 信号点:
        macd = compute_macd(klines)    # {"dif","dea","hist"} → DIF vs DEA 判方向
        ma = compute_ma(klines)        # {5,20,...} → MA5 vs MA20
        rsi = compute_rsi(klines)      # {14} → vs 50
        kdj = compute_kdj(klines)      # K vs D
        extreme = await compute_extreme(ch, sym, klines)   # ★PR-1 提取的 service 函数(perp 极端)
        atr = compute_atr(klines, 14)  # 止损用
        # 布林方向分另读 boll:snapshot:latest 的 bias(权重2.0·不在本快照重算)
        rows.append({"symbol": sym, "macd_dir": _dir(macd), "ma_dir": ...,
                     "rsi": rsi[14], "atr": atr, "extreme_dir": ..., ...})
    payload = json.dumps({"as_of": datetime.now(tz=UTC).isoformat(), "items": rows},
                         ensure_ascii=False)
    await redis.set("intelligent:signals:latest", payload, ex=30*60)   # boll_scan.py:214 范式
```
- **beat 注册**(celery_config.py):`crontab(minute="3,18,33,48")` + `{"expires": 600}`(和 boll_scan 同频)
- **读快照范式**(PR-3/4 用):`json.loads(await redis.get(key))["items"]`(仿 managed/close.py:_read_bias_map)
- **item 设计**:每币嵌套各扫描器 `{buy_triggered, sell_triggered, value}` + atr + change_pct_24h(供 PR-3 打分)

★**worker 取 CH/Redis client**:CH 用 `ClickHouseClient.create()` 或裸 `clickhouse_connect.get_async_client`(managed_trading.py:_get_raw_ch)· Redis 用 `aioredis.from_url(..., decode_responses=True)`。

---

## 6. PR-1~6 实现要点速查(每 PR 用现成什么)

- **PR-1 信号生产**:新 worker task `intelligent_signals_scan`(仿 boll_scan)· 调 `scan_signals`×5 + 提取的 `compute_extreme` + `compute_atr` · 存 `intelligent:signals:latest` · ★唯一碰现有代码 = 提取 `_scan_extreme_for` 成 service
- **PR-2 地基**:照搬 managed account/guard · 迁移加 intelligent/intelligent_close_reason 列 · ★金额可改/清零重来(managed 也补)
- **PR-3 策略引擎**:读两快照(boll+signals)→ 各指标打分 → 加权求和 → ±3.0 开多/空 · `compute_atr` → 止损/止盈价(纯函数·可纯单测)
- **PR-4 开仓**:`run_intelligent_open` → `route_open_perp`(LONG/SHORT·100U/5x)+ 标 intelligent · 记开仓共振信号
- **PR-5 平仓**:`run_intelligent_close` → ATR止损/止盈2:1/信号反转 → `route_close_perp` · ★保留强平兜底(intelligent 仓 managed=False 自然进强平)
- **PR-6 看板**:照搬 managed page.tsx · 加总敞口/做多做空区分/每笔开仓信号 · 账户管理(金额改/清零)
- **PR-7+ (二期)**:DeepSeek 日/周/月复盘

---

## 附:本调研未做(留给各 PR)
- 未设计具体打分权重/阈值(PR-3 定)· 未碰任何业务代码 · 未建实现分支
- `_scan_extreme_for` 提取 + item 字段终稿在 PR-1 定 · 开仓信号记录 schema(JSON 列 vs 单独表)在 PR-4 定
