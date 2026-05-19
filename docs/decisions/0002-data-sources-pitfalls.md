# 数据层翻车清单 · 0002

> 实战踩坑边踩边记。每条:**问题 → 排查 → 修复 → 防御层**。
> Task 2 / Task 4.3 / Task 2.6 接告警时把这里列出的关键词 grep stdout 直接对得上。

## 0. 状态
Open · 持续更新(2026-05-19 起)

---

## 1. ClickHouse `default` 用户从 25.x 起默认需要密码

### 问题
D5 集成测试连接 ClickHouse 5/5 全 skip,提示 `DatabaseError: Authentication failed: password is incorrect, or there is no user with such name. (REQUIRED_PASSWORD)`(code 194)。

### 排查
- Checkpoint B 的自验用的是 `docker compose exec clickhouse clickhouse-client ...`,**容器内 localhost 走的是 native protocol 9000,默认不校验 default 用户密码**
- 从 host 走 HTTP 8123 是另一条路径,**会强制校验**
- ClickHouse 25.x 起 entrypoint 给 `default` 用户自动生成随机密码,写入 `/etc/clickhouse-server/users.d/default-password.xml`

### 修复
- docker-compose `clickhouse` 服务显式设置 `CLICKHOUSE_USER=midas` + `CLICKHOUSE_PASSWORD=midas_dev`,绕过自动随机密码逻辑
- 同步加 `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1` 让该用户拥有完整权限
- `apps/api/app/core/config.py` 加 `clickhouse_user` + `clickhouse_password` 字段
- `ClickHouseClient.create()` 把这两项传给 `clickhouse_connect.get_async_client`
- 必须 `docker compose down -v` 清旧 volume,否则旧的 `users.d/` 还在

### 防御层
- D 阶段已加(进 0002)
- 后续 Checkpoint B 类的「基础设施验收」应该**至少包含一次从 host 8123 的 HTTP 拨号**,而不只是 exec 进容器跑命令

---

## 2. ClickHouse session timezone 默认非 UTC,naive DateTime 会被悄悄转换

### 问题
ClickHouseClient round-trip 测试看到时间偏移 8 小时:写入 `Kline.ts=2026-05-04 00:00 UTC`,读出却变成 `2026-05-03 16:00 UTC`。导致 `test_insert_skips_duplicates`、`test_select_with_since` 全挂。

### 排查
- `Kline.ts` 是 tz-aware UTC,我用 `_to_naive_utc` 剥掉 tz 写入 CH DateTime 列
- CH DateTime 列内部存 Unix epoch 秒,naive 入参以 **session timezone** 解释
- clickhouse-connect 默认从 server 读 timezone(`clickhouse/clickhouse-server:latest` 26.4.2 在我的 Mac docker 环境下被推断为 CN +8)
- 写入时把 naive 2026-05-04 00:00 当作 CN 本地时间 → epoch 2026-05-03 16:00 UTC
- 读出时 clickhouse-connect 再以 server tz 转换 → 给回 Python 的 naive 2026-05-03 16:00,我代码加 `tzinfo=UTC` → 错位 8 小时

### 修复
- `ClickHouseClient.create()` 显式 `settings={"session_timezone": "UTC"}`,锁死会话时区
- 这样 naive datetime 一致按 UTC 解释,写入/读出无偏移
- 表结构无需改(继续用 `DateTime` 而非 `DateTime('UTC')`,免迁移)

### 防御层
- D 阶段已加:`session_timezone='UTC'` 写进 `ClickHouseClient.create()` 参数里
- 测试 round-trip 用 8 小时偏移敏感的 ts 抓回归
- 后续若改连 ClickHouse Cloud 或不同 server,**别忘了带这条 session setting**

---

## 3. clickhouse-connect 把 naive datetime 按 OS 本地 TZ 转 UTC

### 问题
即便 server_timezone=UTC + session_timezone=UTC,集成测试还是出现 8 小时偏移。

### 排查(用 toUnixTimestamp 直接看存的 epoch)
- 插入 **naive** `2026-05-04 00:00` → CH 存 epoch=`1777824000` = **2026-05-03 16:00 UTC**(偏 -8h)
- 插入 **tz-aware UTC** `2026-05-04 00:00 UTC` → CH 存 epoch=`1777852800` = **2026-05-04 00:00 UTC** ✓
- 用 SQL 字符串 `'2026-05-04 00:00:00'` 插入 → 同样正确
- 系统:`time.tzname=('+08', '+08')`,OS 在 CN

### 根因
clickhouse-connect 1.0 在序列化 naive datetime 时调用 `datetime.astimezone()`,
**Python 的 astimezone 对 naive 假设其为系统本地时区**,因此 CN 系统会把
`2026-05-04 00:00 naive` 当成 CN local → 转成 UTC 后变 `2026-05-03 16:00 UTC`。
跟 server / session 的 timezone 设置无关——错误发生在 Python 客户端序列化阶段。

### 修复
- `_to_naive_utc` 重命名为 `_to_aware_utc`,返回 **tz-aware UTC datetime**
- insert / 查询参数全部传 tz-aware
- select 返回的 naive datetime 用 `replace(tzinfo=UTC)` 补回

### 防御层
- **铁律:不要给 clickhouse-connect 传 naive datetime,永远传 tz-aware**
- 后续所有数据源适配器返回的 `Kline.ts` 必须是 tz-aware(Pydantic schema 强校验 `AwareDatetime` 已经把这条变成静态约束)
- 这条对 PostgreSQL / asyncpg 不成立(那边有不同的处理),不要混淆

---

## 4. AKShare EastMoney 端点不稳,改 Sina 做主路径

### 问题
E1 实测 `ak.stock_zh_a_hist(symbol="600519", period="daily")` 一直挂在
`('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))`。
4 次重试 + 1/5/15s 退避全失败。

### 排查
- 直接 `curl https://push2his.eastmoney.com/api/qt/stock/kline/get` → `(52) Empty reply from server`(0 字节响应,服务端直接拒)
- 同一时刻 ccxt Binance / yfinance NVDA 全部正常 —— 不是 general 网络问题
- 切换 `ak.stock_zh_a_daily(symbol="sh600519")`(Sina 通道)→ ✓ 立刻返回完整 DataFrame

结论:**EM 的 `push2his.eastmoney.com` 高频 K 端点对我这个 IP 当前 5xx 或限流**。
不是代码问题,是上游问题,但既然 Sina 同时可用,不应该让用户也跟着卡。

### 修复
`apps/api/app/services/data_sources/cn_source.py`:
- 日 K / 周 K → 走 **Sina** (`stock_zh_a_daily`,symbol 加 `sh/sz` 前缀)
- 分钟 K (1m/5m/15m/30m/1h) → 仍走 **EM**(Sina 不提供股票分钟 K)
- 标的列表 → 走 `stock_info_a_code_name`(EM 但不同接口,目前稳)
- Sina 返回 volume 单位是 **股**,在适配器层除 100 归一到 **手**(A 股标准)

### 防御层
- EM 路径仍保留,但只服务分钟 K
- 若分钟 K 也长期挂,需要降级方案(M0 不做,留给 Task 2.6 监控 + 告警)
- 0002 后续若发现 Sina 也挂,记录第二个 fallback(腾讯 / 中财网)
- **不要把 Sina 当唯一来源:** Sina 没有分钟 K + 没有最新 1 个交易日的早盘数据(午盘后才更新),局限性写进 stdout 日志

### 为什么不做后端聚合(2026-05-19 产品负责人拍板)

考虑过的方案:600519 EM 不稳时,从 1d K 聚合出 1w K(SQL `GROUP BY toMonday(ts)`),
绕过上游不稳定。否决,理由:

1. **15m / 1h 无法从 1d 聚合**(信息量不存在;1d 的 OHLC 是日内全量压缩,
   反推不出小时内 OHLC),所以聚合**只解决 1/3 的空档**,不彻底
2. **聚合 1w 跟交易所原生 1w 有边界差异:**
   - 交易所 1w 通常以"自然周首日"为锚(国内交易所:周一 09:30 起;美股 / Binance 类似)
   - 我自己 GROUP BY 出来的 1w,如果起点定义不一致(比如取周日 00:00 UTC),
     跟前端 KLineChart 显示的"标准周 K"对不上,容易让用户误以为是 bug
   - 跨市场聚合规则要为 cn/us/crypto 各写一套,工程量超过 M0 范围
3. **M0 接受空数据态 + 前端友好提示更工程化:**
   - 前端用 `EmptyKline` 占位卡(详见 docs/decisions/0005-empty-data-state.md),
     文案体贴(「该周期数据回填中」+ 一键切到日 K),不让用户撞错
   - 真正的修复路径是上游问题 —— EM 端点稳定 / 引入第二 fallback(腾讯/中财网)/
     最终接 Tushare 等付费源(M2+ 再说)

**保留判断空间的边界:** 如果 Task 4 自选股 / Task 5 虚拟交易里出现「**因为 1h K 缺数据
导致用户体验严重崩**」的场景,届时重新评估「日内聚合 + 标注 来自聚合」是否值得做。

---

## 5. Celery `autodiscover_tasks` 不适配扁平 `tasks/<feature>.py` 布局

### 问题
F4 worker beat 启动后,日志疯狂报 `Received unregistered task of type 'tasks.incremental.update_crypto_demo'`,任务被 broker 派发但 worker 无法解析。

### 排查
- Manus 留下的 `celery_app.py` 用 `app.autodiscover_tasks(["tasks"])`
- 该函数源自 Django `INSTALLED_APPS` 风格,它扫描每个"app" 下的 `tasks.py` 文件
  (即查找 `tasks/tasks.py`,我们的文件叫 `tasks/incremental.py`,扫不到)
- `data_ingest` 之前没被调度过,所以这个问题在 F3 阶段没暴露
- F4 beat 把 incremental 任务排队后,worker consumer 找不到 strategy → 报错

### 修复
`apps/worker/celery_app.py`:
```python
# 删掉 autodiscover_tasks(...)
from tasks import data_ingest, incremental  # noqa: F401 -- register @shared_task
```

显式 import 任务模块,在 Celery app 创建后触发 `@shared_task` 装饰器副作用。

### 防御层
- Celery beat schedule 里挂的每个 task 在新增模块后**必须确认有显式 import** ——
  这条对 autodiscover 是 hidden 假设,不挂任务永远暴不出来
- 后续新加 `tasks/<x>.py` 时,要么在 `celery_app.py` 加一行 import,
  要么改用真正的 `autodiscover_tasks([具体的包路径])`

---

## 6. ClickHouse `Date` 列非 nullable,`None` 写入会被 clickhouse-connect 翻车

### 问题
F5 跑 `python -m tasks.data_ingest` 演示回填时:
```
TypeError: unsupported operand type(s) for -: 'NoneType' and 'datetime.date'
  File "clickhouse_connect/datatypes/temporal.py", in _write_column_binary
    column = [(x - esd).days for x in column]
```

### 排查
- `SymbolMeta.listed_date: date | None = None`(我们的 schema 允许)
- ClickHouse `symbol_meta.listed_date` 列声明为 `Date`(非 Nullable)
- clickhouse-connect 序列化时直接 `(x - epoch_start_date).days`,x=None 报错
- 美股 / 加密 demo 标的没有 listed_date,踩到这个 None 路径

### 修复
- `apps/api/app/services/clickhouse_client.py`:写入时 None → 哨兵 `date(1970, 1, 1)`
  (CH Date 列合法起点);读出时这个值翻译回 None
- 不改 CH schema(免迁移)

### 防御层
- **铁律:写入 CH 非 nullable 列前,所有 None 必须显式替换为该类型的哨兵或默认值**
- 后续如果 schema 设计想要表达「未知」语义,优先 `Nullable(T)` 而非占位哨兵
  —— 但 M0 阶段两个都接受,只要文档化清楚

---

## 7. AKShare `stock_zh_a_daily` 不接受 `period` 参数,1w K 必须走 EM

### 问题
Task 3 启动前的预热运行 `python -m tasks.data_ingest --all-periods` 时,600519 / 1w 报:
```
TypeError: stock_zh_a_daily() got an unexpected keyword argument 'period'
```

### 排查
- 我在 E1 阶段以为 `stock_zh_a_daily(symbol, period="weekly")` 支持周 K(类比 EM 的
  `stock_zh_a_hist(period="weekly")`),实际 AKShare 这两个函数签名**不一样**
- `ak.stock_zh_a_daily` 只接受 `(symbol, start_date, end_date, adjust)`,**无 period**
- E1 阶段只测了 1d,所以 1w 这条路径根本没真跑过(单元测试 mock 了 `stock_zh_a_daily`,
  也没暴露签名问题)

### 修复
`apps/api/app/services/data_sources/cn_source.py`:
- `_SINA_DAILY` 只保留 `{"1d": None}`,Sina 路径专门跑日 K
- 新增 `_EM_DAILY_LIKE = {"1w": "weekly"}` 路径,走 EM `stock_zh_a_hist(period="weekly")`
- 新增 `_fetch_em_daily_like` + `_em_daily_df_to_klines`(字段 `日期/开盘/收盘/...`,与 minute K 的 `时间` 不同)
- `_fetch_sina_daily` 签名去掉 period 参数

**注意:** EM 路径继承翻车 4 的不稳定性。1w 数据可能拉不到。M0 demo 接受这条限制。

### 防御层
- **铁律(扩展):** 不要假设 SDK 同一族函数的签名是一致的。每条新路径(每个 period × 每家上游)
  都要在 E 阶段真打一次,否则可能踩这种「mock 单测过,集成实测炸」的坑(对应 0002 F 总结 P1)
- 后续如新增 monthly K / yearly K,需要单独验证 AKShare 哪个函数支持

---

## 8. 前端 TanStack Query × 后端 BaseDataSource._retry 双层重试,失败时长翻倍

### 问题
H Checkpoint playwright 截图,600519/15m 等了 25s 仍显示空白 chart(预期 EmptyKline)。
直接 curl `/api/v1/market/kline?symbol=600519&market=cn&period=15m` 实测 22s 返回 503。
但前端等到 44s+ 才进 EmptyKline。

### 排查
- 后端 BaseDataSource._retry 已做 4 次尝试,1/5/15s 指数退避 ≈ 21s + 调用时长 ≈ 22s 确定 503
- 前端 useKline 设置了 `retry: 1`,TanStack Query 又额外重试 1 次
- 双层叠加:前端总等 ≈ 44s 才把 query.status 变 'error',EmptyKline 才出现
- 期间 query.status='pending',KlineChart 落到 `<div>` 分支,klinecharts 已 init 一个空 canvas → 用户看到「带 Y 轴的空图」,不是 EmptyKline

### 修复
`apps/web/hooks/use-kline.ts`:
- `retry: 1` → `retry: 0`
- 后端已经在做指数退避重试,前端没必要叠加 —— 后端失败 = 立刻向用户显示

### 防御层
- **铁律:retry 只在最贴近 transport 的一层做**,不要分层叠加
  (我们是后端做,前端不重试;反过来也行,但不能两层都做)
- 进 useQuery / useSWR / 类似 client 状态库时,默认 retry 配置必须显式设 0 或评估后写明
- 这条对 Task 4 自选股(WebSocket 重连)/ Task 6 通知发送 / 所有 RPC 调用都成立

D / E 阶段都是单一模块自验,翻车都是**模块内部**;F 阶段把 D + E + 数据库 + worker
+ FastAPI 全栈拼装起来,踩的两次坑(翻车 5 + 6)都**发生在接缝**。提炼成 4 条通用
预防策略,后续 Task 3-6 组装期对照检查:

### P1 · 接缝处必有翻车,组装期专门留 buffer
- D / E 单元测试全过 ≠ F 端到端通。每条新连线(API ↔ DB / worker ↔ API / front ↔ back)都要单独跑一次实测。
- 翻车 5(Celery autodiscover)和 6(CH listed_date None)都是「文档/代码默认行为 ≠ 我们布局/数据假设」。
- **应用:** Task 3 G Checkpoint 后第一件事就是端到端打通"前端 → /kline → 渲染",不只是组件单测。

### P2 · 用 framework 默认配置前,验证它的隐式假设
- `autodiscover_tasks(["tasks"])` 隐式假设 `tasks/tasks.py`,我们的布局是 `tasks/<feature>.py`,没对上就静默不挂载,**直到 beat 触发才暴露**。
- 同理:`clickhouse_connect.insert(...)` 隐式假设输入是该列类型的合法值,None 不算合法。
- **应用:** 用任何 "convention over configuration" 的 API,先读它的 convention,再决定要不要走默认。

### P3 · Nullable 边界必须显式跨越
- Pydantic schema 允许 `field: T | None`,**但持久层(SQLAlchemy / ClickHouse)的列可能非空**。
- 翻车 6 就是 `SymbolMeta.listed_date: date | None` 撞 CH `Date`(非 Nullable)。
- **应用:** 设计 schema 时给每个可空字段问一遍:存储层接受 None 吗?不接受就在写入层加哨兵/默认值映射。下游读出时反映射回 None。

### P4 · 数据流终态用 SQL/工具直接看,别只看 Python 层
- 翻车 3 我们用 `toUnixTimestamp(ts)` 直接看 CH 存的 epoch,才发现 -8h 偏移是 client 序列化(不是 server)的锅。
- 翻车 6 也是看 `SELECT listed_date FROM symbol_meta` 直接看了哨兵值生效。
- **应用:** 调试存储层问题,**不要只看 Python 模型/dataclass 打印**,直接用 SQL / `clickhouse-client` / `psql` 看二进制层的真值。这条来自产品负责人 F 阶段的反馈。
