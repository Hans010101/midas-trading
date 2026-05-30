#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# ADR 0034a · 港股阶段一 P1-1 · CH market Enum8 【回滚】
# ═══════════════════════════════════════════════════════════════════════
# ★★ 重要事实(已在 CH 26.4.2.10 实测)★★
#   迁移(加 'hk'=4)是【加值 · metadata-only · 无害】:旧 cn/us/crypto 数据/分区都没动,
#   没有 hk 数据时整个变更对系统零影响。
#   而「MODIFY 收窄回 3 值」在 kline 和 symbol_meta 上【都会被 CH 拒】:
#     Code: 524 ALTER_OF_COLUMN_IS_FORBIDDEN — market 在 kline 是【分区键】、在 symbol_meta
#     是【排序键】,CH 禁止可能改变 key 表示的收窄。→ 回滚【不能】靠 ALTER MODIFY。
#
# 所以回滚分两种:
#   ① 推荐:【什么都不做,留着 4 值】。无 hk 数据时完全无害,后续要用 hk 也省得再迁。
#   ② 确需把 'hk'=4 从类型里抹掉(严格洁癖):只能【整表重建】(CREATE 3值 → INSERT SELECT
#      排除 hk → EXCHANGE 原子交换 → DROP 旧表)。重 + 有风险 → 本脚本只【打印指引不自动执行】。
#
# 本脚本职责:查 hk 数据现状 + 打印两种回滚指引;不自动跑破坏性重建。
# 运行:CLICKHOUSE_PASSWORD=<CH密码> bash scripts/hk-phase1/rollback_ch_market_enum.sh
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

CH_CONTAINER="${CH_CONTAINER:-midas-clickhouse}"
CH_DB="${CH_DB:-default}"
CH_USER="${CH_USER:-midas}"
CH_PASSWORD="${CLICKHOUSE_PASSWORD:-}"
ENUM3="Enum8('cn' = 1, 'us' = 2, 'crypto' = 3)"

[ -z "$CH_PASSWORD" ] && { echo "用法:CLICKHOUSE_PASSWORD=xxx bash $0"; exit 1; }
# ★ 故意【不加】docker exec 的 -i(详见 migrate_ch_market_enum.sh 注释 · 防 Code 48 + 不抢终端 stdin)
chq() { docker exec "$CH_CONTAINER" clickhouse-client --user "$CH_USER" --password "$CH_PASSWORD" --database "$CH_DB" --query "$1"; }

echo "ADR0034a P1-1 · CH market Enum8 回滚指引 · db=${CH_DB} · 目标 CH 26.4.2.10"

# 1. 查 market 列现状 + hk 数据量
echo ""
echo "现 market 列类型:"
chq "SELECT table, type FROM system.columns WHERE database='${CH_DB}' AND table IN ('kline','symbol_meta') AND name='market' FORMAT PrettyCompactMonoBlock"
HK_KLINE=$(chq "SELECT count() FROM ${CH_DB}.kline WHERE market = 'hk'")
HK_META=$(chq "SELECT count() FROM ${CH_DB}.symbol_meta WHERE market = 'hk'")
echo "现有 hk 数据:kline=${HK_KLINE} 行 · symbol_meta=${HK_META} 行"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "① 推荐回滚:【什么都不做】"
echo "   加 'hk'=4 是加值 · metadata-only · 无害。无 hk 数据时对系统零影响。"
echo "   不用、也不该 MODIFY 收窄(CH 会报 Code 524,market 是 key 列)。直接留着即可。"
echo "════════════════════════════════════════════════════════════"

if [ "${HK_KLINE}" = "0" ] && [ "${HK_META}" = "0" ]; then
  echo ""
  echo "当前【无 hk 数据】→ 强烈建议走 ①(留着 4 值,收工)。"
else
  echo ""
  echo "⚠ 当前【已有 hk 数据】(kline=${HK_KLINE} / meta=${HK_META})→ 走 ② 重建会【丢弃这些 hk 行】,确认你要丢。"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "② 确需把 'hk'=4 从类型里抹掉:只能整表重建(★ 手动执行 · 低峰 + 停 worker)"
echo "   原理:MODIFY 收窄被 CH 禁 → 新建 3 值表 → 把非 hk 行灌进去 → EXCHANGE 原子换名 → 删旧表。"
echo "   kline(分区键 (market,toYear(ts))· ORDER BY (symbol,period,ts)· 有 instrument 列):"
echo "     CREATE TABLE ${CH_DB}.kline_v3 AS ${CH_DB}.kline;   -- 复制结构(含分区/排序/列)"
echo "     ALTER TABLE ${CH_DB}.kline_v3 MODIFY COLUMN market ${ENUM3};  -- 空表上收窄 OK(无数据无 key 表示问题)"
echo "     INSERT INTO ${CH_DB}.kline_v3 SELECT * FROM ${CH_DB}.kline WHERE market != 'hk';"
echo "     EXCHANGE TABLES ${CH_DB}.kline AND ${CH_DB}.kline_v3;  -- 原子交换(Atomic 库默认支持)"
echo "     DROP TABLE ${CH_DB}.kline_v3;   -- 确认新 kline 无误后再删"
echo "   symbol_meta(排序键 (market,symbol)· ReplacingMergeTree):同法,表名换 symbol_meta。"
echo "   ★ 大表重建耗时/占盘;务必低峰 + 停采集 worker + 先备份;每步确认后再下一步。"
echo "   ★ 演练:rehearse_ch_migration_testdb.sh 步骤 6 已在临时库验证重建+EXCHANGE 可行。"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "(本脚本只读 + 打印指引,未改任何库;② 的重建请你手动逐条执行。)"
