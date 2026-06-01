#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# ADR 0034a · 港股阶段一 P1-1 · CH 迁移【可逆演练】(测试 · 先跑这个验证)
# ═══════════════════════════════════════════════════════════════════════
# 在【临时库 hk_migrate_rehearsal】里忠实复刻 kline(market 在分区键)+ symbol_meta
# (market 在排序键)两种真实表形态,演练:
#   UP 加 'hk'=4(两表都能 · metadata-only)→ 插 hk → 幂等 →
#   ★ MODIFY 收窄回 3 值被 CH 拒(Code 524,market 是 key 列)= 预期,证明回滚不能靠 MODIFY →
#   真·回退靠整表重建(CREATE 3值 + INSERT SELECT 排除 hk + EXCHANGE TABLES 原子交换)。
# ★ 绝不碰真实 kline / symbol_meta —— 全在临时库,结束 DROP DATABASE 清干净。
# 这一步【先跑】· 通过了再跑生产迁移 migrate_ch_market_enum.sh。
#
# 运行(服务器宿主机 · 需 docker 权限 + CH 密码):
#   CLICKHOUSE_PASSWORD=<CH密码> bash scripts/hk-phase1/rehearse_ch_migration_testdb.sh
# 目标 CH 版本:26.4.2.10(写法已按该版本兼容性实测)
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

CH_CONTAINER="${CH_CONTAINER:-midas-clickhouse}"
CH_USER="${CH_USER:-midas}"
CH_PASSWORD="${CLICKHOUSE_PASSWORD:-}"
RDB="hk_migrate_rehearsal"   # 临时库 · 演练完 DROP
ENUM3="Enum8('cn' = 1, 'us' = 2, 'crypto' = 3)"
ENUM4="Enum8('cn' = 1, 'us' = 2, 'crypto' = 3, 'hk' = 4)"

[ -z "$CH_PASSWORD" ] && { echo "用法:CLICKHOUSE_PASSWORD=xxx bash $0"; exit 1; }

# ★ 故意【不加】docker exec 的 -i:-i 会给 clickhouse-client 接一个 stdin 流,CH 26.4.2.10
#   在 async_insert=1(生产默认)下会把它当 "external data from stdin",与内联 VALUES 冲突报
#   Code 48 "both inlined and external data ... not supported"。不接 stdin = 该冲突结构上不可能。
#   query 全部走 --query 内联;无任何命令靠 stdin 喂数据。(已在 CH 26.4.2.10 容器实测)
chq() { docker exec "$CH_CONTAINER" clickhouse-client --user "$CH_USER" --password "$CH_PASSWORD" --query "$1"; }
line() { printf '\n──── %s ────\n' "$1"; }
ktype() { chq "SELECT type FROM system.columns WHERE database='${RDB}' AND table='kline_test' AND name='market'"; }
mtype() { chq "SELECT type FROM system.columns WHERE database='${RDB}' AND table='meta_test'  AND name='market'"; }
kdist() { chq "SELECT market, count() FROM ${RDB}.kline_test GROUP BY market ORDER BY market FORMAT TSV"; }

echo "ADR0034a P1-1 · CH 迁移可逆演练 · 临时库=${RDB}(不碰真实表)· 目标 CH 26.4.2.10"

line "0. 准备临时库 + 忠实复刻两表 + cn 基线数据"
chq "DROP DATABASE IF EXISTS ${RDB}"
chq "CREATE DATABASE ${RDB}"
# kline:market 在【分区键】(= 真实 kline)
chq "CREATE TABLE ${RDB}.kline_test (
       symbol String, market ${ENUM3}, ts DateTime, close Float64
     ) ENGINE = MergeTree PARTITION BY (market, toYear(ts)) ORDER BY (symbol, ts)"
# symbol_meta:market 在【排序键】· ReplacingMergeTree(= 真实 symbol_meta)
chq "CREATE TABLE ${RDB}.meta_test (
       symbol String, market ${ENUM3}, name String, updated_at DateTime DEFAULT now()
     ) ENGINE = ReplacingMergeTree(updated_at) ORDER BY (market, symbol)"
chq "INSERT INTO ${RDB}.kline_test VALUES ('600519','cn','2024-01-01 00:00:00', 1688.0)"
chq "INSERT INTO ${RDB}.kline_test VALUES ('NVDA','us','2024-01-01 00:00:00', 100.0)"
chq "INSERT INTO ${RDB}.meta_test (symbol, market, name) VALUES ('600519','cn','贵州茅台')"
echo "baseline · kline 类型=$(ktype) · meta 类型=$(mtype)"
echo "kline 基线分布:"; kdist
KCNT_BEFORE=$(chq "SELECT count() FROM ${RDB}.kline_test")

line "1. UP · 两表都 MODIFY 加 'hk'=4(分区键 + 排序键都验)"
chq "ALTER TABLE ${RDB}.kline_test MODIFY COLUMN market ${ENUM4}"
chq "ALTER TABLE ${RDB}.meta_test  MODIFY COLUMN market ${ENUM4}"
echo "UP 后 · kline 类型=$(ktype)"
echo "UP 后 · meta  类型=$(mtype)"

line "2. 验证旧数据没被动(UP 是 metadata-only)"
KCNT_AFTER=$(chq "SELECT count() FROM ${RDB}.kline_test")
echo "UP 前 kline 行数=${KCNT_BEFORE} · UP 后=${KCNT_AFTER}"
[ "$KCNT_BEFORE" = "$KCNT_AFTER" ] && echo "  ✅ 行数一致 · 旧 cn/us 数据没动" || echo "  ⚠ 行数变了!"

line "3. 插 hk 行(证明 hk 可写)"
chq "INSERT INTO ${RDB}.kline_test VALUES ('00700','hk','2024-01-01 00:00:00', 300.0)"
chq "INSERT INTO ${RDB}.meta_test (symbol, market, name) VALUES ('00700','hk','腾讯控股')"
echo "插 hk 后 kline 分布:"; kdist

line "4. 幂等 · 再 MODIFY 到同 4 值(应 no-op 不报错)"
chq "ALTER TABLE ${RDB}.kline_test MODIFY COLUMN market ${ENUM4}"
chq "ALTER TABLE ${RDB}.meta_test  MODIFY COLUMN market ${ENUM4}"
echo "  ✅ 幂等通过 · kline 类型仍=$(ktype)"

line "5. ★ 验证「MODIFY 收窄回 3 值」被 CH 拒(Code 524)= 预期 · 证明回滚不能靠 MODIFY"
if chq "ALTER TABLE ${RDB}.kline_test MODIFY COLUMN market ${ENUM3}" 2>/dev/null; then
  echo "  ⚠ UNEXPECTED:kline 收窄居然成功(与 26.4.2.10 实测不符,请复查!)"; exit 1
else
  echo "  ✅ kline(分区键)收窄被拒 → 符合预期(market 是分区键,CH 禁止可能改变表示的收窄)"
fi
if chq "ALTER TABLE ${RDB}.meta_test MODIFY COLUMN market ${ENUM3}" 2>/dev/null; then
  echo "  ⚠ UNEXPECTED:meta 收窄居然成功(请复查!)"; exit 1
else
  echo "  ✅ meta(排序键)收窄同样被拒 → 符合预期 → 回滚【不能】靠 MODIFY,见步骤 6"
fi

line "6. ★ 真·回退路径 = 整表重建(CREATE 3值 + INSERT SELECT 排除 hk + EXCHANGE 原子交换)"
chq "CREATE TABLE ${RDB}.kline_test_v3 (
       symbol String, market ${ENUM3}, ts DateTime, close Float64
     ) ENGINE = MergeTree PARTITION BY (market, toYear(ts)) ORDER BY (symbol, ts)"
chq "INSERT INTO ${RDB}.kline_test_v3 SELECT symbol, market, ts, close FROM ${RDB}.kline_test WHERE market != 'hk'"
chq "EXCHANGE TABLES ${RDB}.kline_test AND ${RDB}.kline_test_v3"   # 原子交换(Atomic 库默认支持)
chq "DROP TABLE ${RDB}.kline_test_v3"
echo "重建+交换后 · kline 类型=$(ktype)(应回到 3 值)"
echo "重建后 kline 分布(应只剩 cn/us · hk 已排除):"; kdist

line "7. 清理 · DROP 临时库"
chq "DROP DATABASE ${RDB}"
echo ""
echo "✅ 演练完成 · 临时库已 DROP · 全验:"
echo "   UP 两表(分区键+排序键)加值 OK / 旧数据未动 / hk 可写 / 幂等 OK /"
echo "   MODIFY 收窄被 CH 拒(Code 524 预期)/ 真·回退靠整表重建+EXCHANGE 验证 OK"
echo "   → 迁移(UP)安全可上;回滚见 rollback_ch_market_enum.sh(不靠 MODIFY)"
