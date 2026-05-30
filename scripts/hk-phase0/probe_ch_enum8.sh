#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# ADR 0034 · 港股接入 · 阶段零-A:ClickHouse market Enum8 迁移【只读探测】
# ═══════════════════════════════════════════════════════════════════════
# ★★ 本脚本只读探测,绝不改库 ★★
#   - 只发 SELECT / SHOW / DESCRIBE(物理上无法改数据/结构)
#   - 绝不执行 ALTER / INSERT / DROP / CREATE / OPTIMIZE / TRUNCATE
#   - 真正的 ALTER(加 'hk'=4)留到阶段一、且带回滚预案;本脚本只输出评估 + 把待执行的
#     ALTER / 回滚语句【echo 成文本】给你看,不发给 ClickHouse。
#
# 目的(零-A):查清现状 + 评估「ALTER MODIFY market Enum8 加 'hk'=4」是否 metadata-only:
#   · kline / symbol_meta 当前 market Enum8 定义、PARTITION/ORDER 键
#   · 数据量 + 分区分布
#   · 给出 metadata-only 判断依据
#
# 运行(在【服务器宿主机】上,需 docker 权限):
#   CLICKHOUSE_PASSWORD=<你的CH密码> bash scripts/hk-phase0/probe_ch_enum8.sh
# 可选覆盖:CH_CONTAINER(默认 midas-clickhouse)· CH_DB(默认 default)· CH_USER(默认 midas)
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

CH_CONTAINER="${CH_CONTAINER:-midas-clickhouse}"
CH_DB="${CH_DB:-default}"
CH_USER="${CH_USER:-midas}"
CH_PASSWORD="${CLICKHOUSE_PASSWORD:-}"

if [ -z "$CH_PASSWORD" ]; then
  echo "⚠ 未设 CLICKHOUSE_PASSWORD 环境变量。用法:CLICKHOUSE_PASSWORD=xxx bash $0"
  echo "  (密码 = 服务器 .env 里的 CLICKHOUSE_PASSWORD · 不要写进脚本/不要提交)"
  exit 1
fi

# 只读查询执行器:每条都是 SELECT/SHOW/DESCRIBE · 不可能写
chq() {
  docker exec -i "$CH_CONTAINER" clickhouse-client \
    --user "$CH_USER" --password "$CH_PASSWORD" --database "$CH_DB" \
    --query "$1"
}

line() { printf '\n══════ %s ══════\n' "$1"; }

echo "ADR0034 零-A · ClickHouse Enum8 只读探测 · 容器=$CH_CONTAINER db=$CH_DB user=$CH_USER"
echo "★ 本脚本只 SELECT/SHOW/DESCRIBE,绝不 ALTER/写任何数据"

line "1. kline 建表语句(看 market Enum8 + PARTITION/ORDER)"
chq "SHOW CREATE TABLE ${CH_DB}.kline"

line "2. symbol_meta 建表语句"
chq "SHOW CREATE TABLE ${CH_DB}.symbol_meta"

line "3. market 列的精确类型(两表)"
chq "SELECT table, name, type FROM system.columns
     WHERE database = '${CH_DB}' AND table IN ('kline','symbol_meta') AND name = 'market'
     FORMAT PrettyCompactMonoBlock"

line "4. 数据量(kline / symbol_meta 行数)"
chq "SELECT 'kline' AS tbl, count() AS rows FROM ${CH_DB}.kline
     UNION ALL
     SELECT 'symbol_meta' AS tbl, count() AS rows FROM ${CH_DB}.symbol_meta
     FORMAT PrettyCompactMonoBlock"

line "5. kline 分区分布(PARTITION BY (market, toYear(ts)))"
chq "SELECT partition, count() AS num_parts, sum(rows) AS rows,
            formatReadableSize(sum(bytes_on_disk)) AS size,
            min(min_time) AS oldest, max(max_time) AS newest
     FROM system.parts
     WHERE database = '${CH_DB}' AND table = 'kline' AND active
     GROUP BY partition ORDER BY partition
     FORMAT PrettyCompactMonoBlock"

line "6. 现有 market 取值分布(确认只有 cn/us/crypto)"
chq "SELECT market, count() AS rows FROM ${CH_DB}.kline GROUP BY market ORDER BY market
     FORMAT PrettyCompactMonoBlock"

line "7. ClickHouse 版本(Enum MODIFY 行为与版本相关)"
chq "SELECT version()"

# ── 评估输出(纯文本 · 不执行)──────────────────────────────────────────
cat <<'ASSESS'

══════ 评估:加 'hk'=4 是否 metadata-only ══════
判断依据:
  · ClickHouse 的 Enum 扩展,若【只新增枚举值、不改已有 name→number 映射】
    (cn=1/us=2/crypto=3 全保留,只追加 hk=4),是 metadata-only ALTER ——
    只改表元数据,不重写已落盘的 parts,不触发重分区(旧分区 market 值映射不变)。
  · 反例(会重写):改了旧值的数字、或删值、或改成不兼容类型 —— 本次都不涉及。
确认方法(阶段一真执行时,不是现在):
  · ALTER 应秒级返回;system.parts 里旧 part 的 modification_time 不应变化。
  · 先在 midas_test 库演练一遍 up→插一条 hk→down→up,验证可逆。

══════ 阶段一【将要执行】的语句(本脚本不执行,仅供你审)══════
-- 迁移(加 hk=4):
--   ALTER TABLE default.kline       MODIFY COLUMN market Enum8('cn'=1,'us'=2,'crypto'=3,'hk'=4);
--   ALTER TABLE default.symbol_meta MODIFY COLUMN market Enum8('cn'=1,'us'=2,'crypto'=3,'hk'=4);
-- 回滚(无 hk 数据时):
--   ALTER TABLE default.kline       MODIFY COLUMN market Enum8('cn'=1,'us'=2,'crypto'=3);
--   ALTER TABLE default.symbol_meta MODIFY COLUMN market Enum8('cn'=1,'us'=2,'crypto'=3);
-- 回滚(已有 hk 数据时):先 ALTER TABLE default.kline DROP PARTITION (hk 分区) 再 MODIFY 回。
-- ⚠ 迁移按决策⑤:低峰执行 + 先停采集 worker · 迁移完恢复。

✅ 零-A 探测完成(只读 · 未改任何库)。把以上输出回贴,据此定迁移可行性。
ASSESS
