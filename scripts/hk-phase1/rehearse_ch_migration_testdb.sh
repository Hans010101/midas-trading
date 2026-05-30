#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# ADR 0034a · 港股阶段一 P1-1 · CH 迁移【可逆演练】(测试 · 先跑这个证可逆)
# ═══════════════════════════════════════════════════════════════════════
# 在【临时库 hk_migrate_rehearsal】里演练 up→插hk→down→up,证明 Enum8 加 'hk'=4 可逆 + 幂等。
# ★ 绝不碰真实 kline / symbol_meta —— 全在临时库的临时表上做,结束 DROP DATABASE 清干净。
# 这一步【先跑】· 通过了再跑生产迁移 migrate_ch_market_enum.sh。
#
# 运行(服务器宿主机 · 需 docker 权限 + CH 密码):
#   CLICKHOUSE_PASSWORD=<CH密码> bash scripts/hk-phase1/rehearse_ch_migration_testdb.sh
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

CH_CONTAINER="${CH_CONTAINER:-midas-clickhouse}"
CH_USER="${CH_USER:-midas}"
CH_PASSWORD="${CLICKHOUSE_PASSWORD:-}"
RDB="hk_migrate_rehearsal"   # 临时库 · 演练完 DROP
ENUM3="Enum8('cn' = 1, 'us' = 2, 'crypto' = 3)"
ENUM4="Enum8('cn' = 1, 'us' = 2, 'crypto' = 3, 'hk' = 4)"

[ -z "$CH_PASSWORD" ] && { echo "用法:CLICKHOUSE_PASSWORD=xxx bash $0"; exit 1; }

chq() { docker exec -i "$CH_CONTAINER" clickhouse-client --user "$CH_USER" --password "$CH_PASSWORD" --query "$1"; }
line() { printf '\n──── %s ────\n' "$1"; }
mtype() { chq "SELECT type FROM system.columns WHERE database='${RDB}' AND table='kline_test' AND name='market'"; }
mdist() { chq "SELECT market, count() FROM ${RDB}.kline_test GROUP BY market ORDER BY market FORMAT TSV"; }

echo "ADR0034a P1-1 · CH 迁移可逆演练 · 临时库=${RDB}(不碰真实表)"

line "0. 准备临时库 + mimic kline 的临时表(3 值 Enum8 · 同分区键)"
chq "DROP DATABASE IF EXISTS ${RDB}"
chq "CREATE DATABASE ${RDB}"
chq "CREATE TABLE ${RDB}.kline_test (
       symbol String, market ${ENUM3}, ts DateTime, close Float64
     ) ENGINE = MergeTree PARTITION BY (market, toYear(ts)) ORDER BY (symbol, ts)"
chq "INSERT INTO ${RDB}.kline_test VALUES ('600519','cn','2024-01-01 00:00:00', 1688.0)"
echo "baseline:类型=$(mtype) · 数据:"; mdist

line "1. up · ALTER 加 'hk'=4(纯加值)"
chq "ALTER TABLE ${RDB}.kline_test MODIFY COLUMN market ${ENUM4}"
echo "up 后类型 = $(mtype)"

line "2. 插一条 hk 行(证明 hk 可插)"
chq "INSERT INTO ${RDB}.kline_test VALUES ('00700','hk','2024-01-01 00:00:00', 300.0)"
echo "插 hk 后分布:"; mdist

line "3. down · 先删 hk 分区(带数据回滚路径)→ 再 ALTER 回 3 值"
chq "ALTER TABLE ${RDB}.kline_test DROP PARTITION ('hk', 2024)"
chq "ALTER TABLE ${RDB}.kline_test MODIFY COLUMN market ${ENUM3}"
echo "down 后类型 = $(mtype)"
echo "down 后数据(应只剩 cn · hk 已随分区删除):"; mdist

line "4. up again · 再加 'hk'=4(证明可逆 + 幂等)"
chq "ALTER TABLE ${RDB}.kline_test MODIFY COLUMN market ${ENUM4}"
chq "ALTER TABLE ${RDB}.kline_test MODIFY COLUMN market ${ENUM4}"   # 再来一次 · 验幂等(MODIFY 到同值 no-op)
echo "再 up(+幂等)后类型 = $(mtype)"

line "5. 清理 · DROP 临时库"
chq "DROP DATABASE ${RDB}"
echo ""
echo "✅ 演练完成 · 临时库已 DROP · 全验:加值 OK / hk 可插 / 带数据 down(删分区+回退)OK / 再 up + 幂等 OK"
echo "   → 可逆性已证 · 可进生产迁移(migrate_ch_market_enum.sh)"
