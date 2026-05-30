#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# ADR 0034a · 港股阶段一 P1-1 · CH market Enum8 【回滚】(把 hk 去掉,回三值)
# ═══════════════════════════════════════════════════════════════════════
# 把 kline + symbol_meta 的 market 列 MODIFY 回 Enum8('cn'=1,'us'=2,'crypto'=3)。
# ★ 安全护栏:若已有 hk 数据 → 直接 MODIFY 回会失败(CH 不允许列里存在 Enum 外的值)→
#   脚本会【中止】并给出"先删 hk 分区"的指引(确认要丢弃这些 hk 数据后再回滚)。
#
# 运行:CLICKHOUSE_PASSWORD=<CH密码> bash scripts/hk-phase1/rollback_ch_market_enum.sh
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

CH_CONTAINER="${CH_CONTAINER:-midas-clickhouse}"
CH_DB="${CH_DB:-default}"
CH_USER="${CH_USER:-midas}"
CH_PASSWORD="${CLICKHOUSE_PASSWORD:-}"
ENUM3="Enum8('cn' = 1, 'us' = 2, 'crypto' = 3)"

[ -z "$CH_PASSWORD" ] && { echo "用法:CLICKHOUSE_PASSWORD=xxx bash $0"; exit 1; }
chq() { docker exec -i "$CH_CONTAINER" clickhouse-client --user "$CH_USER" --password "$CH_PASSWORD" --database "$CH_DB" --query "$1"; }

echo "ADR0034a P1-1 · CH market Enum8 回滚 · db=${CH_DB}"

# 1. 检查是否已有 hk 数据
HK_KLINE=$(chq "SELECT count() FROM ${CH_DB}.kline WHERE market = 'hk'")
HK_META=$(chq "SELECT count() FROM ${CH_DB}.symbol_meta WHERE market = 'hk'")
echo "现有 hk 数据:kline=${HK_KLINE} 行 · symbol_meta=${HK_META} 行"

if [ "${HK_KLINE}" -gt 0 ] || [ "${HK_META}" -gt 0 ]; then
  echo ""
  echo "⚠ 已有 hk 数据 → 不能直接 MODIFY 回三值(列里有 'hk' 会被新 Enum8 拒)。"
  echo "  若【确认要丢弃这些 hk 数据】再回滚,先删 hk 分区:"
  echo "  ① 查 hk 分区名:"
  echo "     docker exec -it ${CH_CONTAINER} clickhouse-client --user ${CH_USER} --password *** --database ${CH_DB} \\"
  echo "       --query \"SELECT DISTINCT partition FROM system.parts WHERE table='kline' AND active AND partition LIKE '%hk%'\""
  echo "  ② 删 hk 分区(每个查到的分区):ALTER TABLE ${CH_DB}.kline DROP PARTITION <分区元组,如 ('hk', 2026)>"
  echo "     symbol_meta 无分区 → DELETE WHERE market='hk'(或重建)· 量极小"
  echo "  ③ 删完再重跑本脚本。"
  echo "已中止(未改任何列定义)。"
  exit 1
fi

# 2. 无 hk 数据 → 确认 → MODIFY 回三值
echo ""
read -rp "无 hk 数据 · 把 market 列回滚到 ${ENUM3}?请输入大写 YES:" REPLY
if [ "$REPLY" != "YES" ]; then echo "已取消(未改库)"; exit 0; fi

chq "ALTER TABLE ${CH_DB}.kline       MODIFY COLUMN market ${ENUM3}"
chq "ALTER TABLE ${CH_DB}.symbol_meta MODIFY COLUMN market ${ENUM3}"
echo "✅ 已回滚 · market 列 = ${ENUM3}"
chq "SELECT table, type FROM system.columns WHERE database='${CH_DB}' AND table IN ('kline','symbol_meta') AND name='market' FORMAT PrettyCompactMonoBlock"
