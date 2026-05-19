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
