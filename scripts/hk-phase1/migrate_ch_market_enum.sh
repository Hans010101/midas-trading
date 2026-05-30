#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# ADR 0034a · 港股阶段一 P1-1 · CH market Enum8 【生产迁移】(★ 会真执行 ALTER)
# ═══════════════════════════════════════════════════════════════════════
# 给 kline + symbol_meta 的 market 列加 'hk'=4(保留 cn=1/us=2/crypto=3 不变)。
# ★★ 只动 market 列【定义】· 绝不 INSERT/DELETE/DROP 任何数据行 ★★
#
# 先决条件(★ 脚本会提醒并要你二次确认,但不自动判定 —— 你负责确认):
#   ① 已在 midas_test 跑过 rehearse_ch_migration_testdb.sh,证可逆
#   ② 低峰窗口(A股/美股/港股都收盘)· 决策⑤
#   ③ 已停采集 worker:docker compose -f <prod compose> stop worker
#
# 运行(服务器宿主机 · 需 docker 权限 + CH 密码):
#   CLICKHOUSE_PASSWORD=<CH密码> bash scripts/hk-phase1/migrate_ch_market_enum.sh
# 出错回滚:见 rollback_ch_market_enum.sh
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

CH_CONTAINER="${CH_CONTAINER:-midas-clickhouse}"
CH_DB="${CH_DB:-default}"
CH_USER="${CH_USER:-midas}"
CH_PASSWORD="${CLICKHOUSE_PASSWORD:-}"
ENUM4="Enum8('cn' = 1, 'us' = 2, 'crypto' = 3, 'hk' = 4)"

[ -z "$CH_PASSWORD" ] && { echo "用法:CLICKHOUSE_PASSWORD=xxx bash $0"; exit 1; }
chq() { docker exec -i "$CH_CONTAINER" clickhouse-client --user "$CH_USER" --password "$CH_PASSWORD" --database "$CH_DB" --query "$1"; }
line() { printf '\n──── %s ────\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "ADR0034a P1-1 · 生产 CH 迁移 · db=${CH_DB} · 只改 kline/symbol_meta 的 market 列定义"

line "1. 前快照(只读)· market 取值分布 + 旧分区 modification_time"
chq "SELECT market, count() FROM ${CH_DB}.kline GROUP BY market ORDER BY market FORMAT TSV" > "$TMP/dist_before.tsv"
chq "SELECT table, partition, count() AS parts, max(modification_time) AS mt
     FROM system.parts WHERE database='${CH_DB}' AND table IN ('kline','symbol_meta') AND active
     GROUP BY table, partition ORDER BY table, partition FORMAT TSV" > "$TMP/parts_before.tsv"
echo "现 market 分布:"; cat "$TMP/dist_before.tsv"
echo "现 market 列类型:"
chq "SELECT table, type FROM system.columns WHERE database='${CH_DB}' AND table IN ('kline','symbol_meta') AND name='market' FORMAT PrettyCompactMonoBlock"

line "2. 将执行的语句(只改列定义)"
echo "  ALTER TABLE ${CH_DB}.kline       MODIFY COLUMN market ${ENUM4};"
echo "  ALTER TABLE ${CH_DB}.symbol_meta MODIFY COLUMN market ${ENUM4};"

line "3. ★ 二次确认"
echo "请确认:① midas_test 已演练过可逆 ② 当前低峰 ③ 已停采集 worker"
read -rp "全部确认无误,执行生产 ALTER?请输入大写 YES:" REPLY
if [ "$REPLY" != "YES" ]; then echo "已取消(未执行任何 ALTER · 库未改)"; exit 0; fi

line "4. 执行 ALTER(仅 market 列定义)"
chq "ALTER TABLE ${CH_DB}.kline       MODIFY COLUMN market ${ENUM4}"
chq "ALTER TABLE ${CH_DB}.symbol_meta MODIFY COLUMN market ${ENUM4}"
echo "✅ ALTER 已执行"

line "5. 后验证 ①:market 列类型已含 hk"
chq "SELECT table, type FROM system.columns WHERE database='${CH_DB}' AND table IN ('kline','symbol_meta') AND name='market' FORMAT PrettyCompactMonoBlock"

line "6. 后验证 ②:旧数据 market 取值分布【前后一致】(旧数据没被动)"
chq "SELECT market, count() FROM ${CH_DB}.kline GROUP BY market ORDER BY market FORMAT TSV" > "$TMP/dist_after.tsv"
if diff -q "$TMP/dist_before.tsv" "$TMP/dist_after.tsv" >/dev/null; then
  echo "  ✅ market 分布前后一致(旧 cn/us/crypto 数据没动)"
else
  echo "  ⚠⚠ market 分布变了!请排查:"; diff -u "$TMP/dist_before.tsv" "$TMP/dist_after.tsv" || true
fi

line "7. 后验证 ③:旧分区 modification_time【前后一致】= metadata-only(没重写数据)"
chq "SELECT table, partition, count() AS parts, max(modification_time) AS mt
     FROM system.parts WHERE database='${CH_DB}' AND table IN ('kline','symbol_meta') AND active
     GROUP BY table, partition ORDER BY table, partition FORMAT TSV" > "$TMP/parts_after.tsv"
if diff -q "$TMP/parts_before.tsv" "$TMP/parts_after.tsv" >/dev/null; then
  echo "  ✅ 分区 modification_time 未变 → metadata-only 确认(没重写已落盘数据)"
else
  echo "  ⚠ 分区 modification_time 有变(可能轻量重写 · 数据量小通常可接受 · 看 diff):"
  diff -u "$TMP/parts_before.tsv" "$TMP/parts_after.tsv" || true
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ 迁移完成。下一步:"
echo "   1) docker compose -f <prod compose> start worker  # 恢复采集"
echo "   2) 观察 worker 日志:现有 cn/us/crypto 采集正常、无报错"
echo "   3) 出问题要回退 → 跑 rollback_ch_market_enum.sh"
echo "════════════════════════════════════════════════════════════"
