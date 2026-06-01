# 港股阶段一 P1-1 · 前置 + CH 迁移脚本(ADR 0034a)

4 个脚本,给 Hans 在服务器跑。**审脚本要点见每个 ★;两个前置过了才真在生产改库。**

| 脚本 | 类型 | 改不改库 |
|---|---|---|
| `probe_hk_latency.py` | 工作日实时延迟补测 | **只读**(只拉上游) |
| `rehearse_ch_migration_testdb.sh` | midas_test 迁移可逆演练 | 只动**临时库**(结束 DROP,不碰真实表) |
| `migrate_ch_market_enum.sh` | ★ **生产迁移**(执行 ALTER · 只 UP 加值) | 只改 kline/symbol_meta 的 **market 列定义**,不碰数据行 |
| `rollback_ch_market_enum.sh` | 回滚【指引】(只读 + 打印,不自动改库) | 不改库(打印「留着 4 值」+ 整表重建指引) |

> **目标 CH 版本 = 26.4.2.10**,所有写法已在该版本容器实测。两条关键兼容性结论:
> ① `docker exec` 调 clickhouse-client **不加 `-i`**(加了会在 `async_insert=1` 下让内联 `INSERT VALUES` 撞 Code 48)。
> ② `market` 在 kline 是分区键、在 symbol_meta 是排序键 → **加值(UP 3→4)允许且 metadata-only,收窄(4→3)被 CH 禁(Code 524)** → 迁移走 ALTER,**回滚不能走 ALTER**(只能整表重建,见下)。

---

## 顺序(严格按这个走)

### 前置 1 · 工作日实时延迟补测(只读)
**工作日 · 港股交易时段(北京 09:30–12:00 / 13:00–16:00)** 跑:
```bash
docker exec -i midas-api python - < scripts/hk-phase1/probe_hk_latency.py
```
看:00700 最新价 + 数据时间戳 + **延迟分钟数**。**延迟 ≤ 15min → 过**(决策③)。

### 前置 2 · midas_test 迁移可逆演练(临时库 · 先证可逆)
```bash
CLICKHOUSE_PASSWORD='<CH密码>' bash scripts/hk-phase1/rehearse_ch_migration_testdb.sh
```
在临时库 `hk_migrate_rehearsal` 演练 up→插 hk→down(删分区+回退)→up,结束自动 DROP 临时库。
全绿(加值/可插/带数据回滚/再加 都 OK)→ **可逆性已证**。**不碰真实表。**

### 生产迁移(★ 两个前置都过 + 低峰 + 已停 worker 后才跑)
```bash
# 0) 低峰窗口(A股/美股/港股都收盘)+ 先停采集 worker:
docker compose -f <prod compose 文件> stop worker
# 1) 跑迁移(会打印前快照 → 要你输 YES 才执行 ALTER → 执行后自动验证):
CLICKHOUSE_PASSWORD='<CH密码>' bash scripts/hk-phase1/migrate_ch_market_enum.sh
# 2) 恢复 worker:
docker compose -f <prod compose 文件> start worker
```
脚本自动验证:① market 类型含 hk ② 旧数据 market 分布前后一致(旧数据没动)
③ 旧分区 modification_time 前后一致(= metadata-only,没重写)。

### 回滚(几乎用不到 · 加值无害)
```bash
CLICKHOUSE_PASSWORD='<CH密码>' bash scripts/hk-phase1/rollback_ch_market_enum.sh
```
脚本**只读 + 打印指引,不自动改库**。两条路:
- **① 推荐:什么都不做**。加 `hk=4` 是 metadata-only,无 hk 数据时零影响,留着即可。
- **② 确需抹掉 `hk=4`**:CH 禁止 `MODIFY` 收窄 key 列(Code 524)→ 只能**整表重建**
  (`CREATE` 3值表 → `INSERT SELECT` 排除 hk → `EXCHANGE TABLES` 原子换 → `DROP` 旧表)。
  脚本会打印 kline / symbol_meta 各自的命令;**手动逐条执行**(重、低峰、先备份)。

---

## 审脚本要点(给产品负责人 / Code review)
- **`migrate` 只 ALTER market 列定义**,全文无 `INSERT/DELETE/DROP` 数据行;唯一写动作是两条 `MODIFY COLUMN`。
- **二次确认**:`migrate` 必须手输大写 `YES` 才执行 ALTER(防误触)。
- **后验证**:migrate 用「前/后快照 diff」证明旧数据 + 分区 modification_time 没变(metadata-only)。
- **rehearse 全在临时库** `hk_migrate_rehearsal`(忠实复刻 kline 分区键 + symbol_meta 排序键两形态),结束 `DROP DATABASE`,**零触碰真实表**;演练含「UP 安全 / 旧数据未动 / hk 可写 / 幂等 / MODIFY 收窄被拒(预期 Code 524)/ 整表重建回退可行」全链路。
- **rollback 不自动改库**:只读 + 打印「留着 4 值(推荐)」与「整表重建(确需)」两套指引,破坏性重建交人手动。
- **不加 `-i` + 无任何 `| tail`**:`chq` 全走 `docker exec`(无 `-i`)防 Code 48;自验取真实 exit code。
- CH 密码只从命令行 env 传,**不写进脚本、不提交**。

## 通过判定 → 进 P1-2
- 前置 1 延迟 ≤15min ✅ + 前置 2 演练可逆 ✅ + 生产迁移后三项验证全绿 ✅
- → 进 **P1-2**(写 `hk_source` + `_source_for` 接入 + init.sql 同步加 hk · 走正常 deploy)。
