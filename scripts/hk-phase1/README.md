# 港股阶段一 P1-1 · 前置 + CH 迁移脚本(ADR 0034a)

4 个脚本,给 Hans 在服务器跑。**审脚本要点见每个 ★;两个前置过了才真在生产改库。**

| 脚本 | 类型 | 改不改库 |
|---|---|---|
| `probe_hk_latency.py` | 工作日实时延迟补测 | **只读**(只拉上游) |
| `rehearse_ch_migration_testdb.sh` | midas_test 迁移可逆演练 | 只动**临时库**(结束 DROP,不碰真实表) |
| `migrate_ch_market_enum.sh` | ★ **生产迁移**(执行 ALTER) | 只改 kline/symbol_meta 的 **market 列定义**,不碰数据行 |
| `rollback_ch_market_enum.sh` | 回滚 | MODIFY market 列回三值(有 hk 数据则中止+指引) |

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

### 回滚(出问题时)
```bash
CLICKHOUSE_PASSWORD='<CH密码>' bash scripts/hk-phase1/rollback_ch_market_enum.sh
```
无 hk 数据 → 输 YES 直接 MODIFY 回三值;有 hk 数据 → 脚本中止 + 给「先删 hk 分区」指引。

---

## 审脚本要点(给产品负责人 / Code review)
- **`migrate` 只 ALTER market 列定义**,全文无 `INSERT/DELETE/DROP` 数据行;唯一写动作是两条 `MODIFY COLUMN`。
- **二次确认**:`migrate` 必须手输大写 `YES` 才执行 ALTER(防误触)。
- **后验证**:migrate 用「前/后快照 diff」证明旧数据 + 分区 modification_time 没变(metadata-only)。
- **rehearse 全在临时库** `hk_migrate_rehearsal`,结束 `DROP DATABASE`,**零触碰真实 kline/symbol_meta**。
- **rollback 有 hk 数据保护**:不会盲目 MODIFY 回导致失败,先提示删分区。
- CH 密码只从命令行 env 传,**不写进脚本、不提交**。

## 通过判定 → 进 P1-2
- 前置 1 延迟 ≤15min ✅ + 前置 2 演练可逆 ✅ + 生产迁移后三项验证全绿 ✅
- → 进 **P1-2**(写 `hk_source` + `_source_for` 接入 + init.sql 同步加 hk · 走正常 deploy)。
