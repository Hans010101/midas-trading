#!/bin/bash
# 点金 Midas · ClickHouse 全量备份 → 阿里云 OSS 香港
# 2026-05-29 · 与 scripts/backup_postgres.sh 同构(OSS 上传 / 凭证 / 日志格式一致)
# 保留口径:RETAIN_DAYS 仅管【本地暂存】清理;OSS 端保留由桶生命周期规则负责(ClickHouse 7 天 · 见 0042)。
#
# 备份内容:default 库下所有 *MergeTree 表(动态枚举 · 新增表自动纳入,不写死白名单)·
#           整库约 151 MiB · 单机一次性导出(已摸底,无需分表流式)。
#   每张表产出三样落到临时工作目录:
#     ① <t>.sql        · SHOW CREATE TABLE(建表语句 · TabSeparatedRaw 真实换行)
#     ② <t>.native.gz  · SELECT * FORMAT Native | gzip -9(二进制零损 · 类型精确)
#     ③ manifest.txt 一行 · 表名<TAB>行数<TAB>压缩字节数(恢复时按行数校验)
#   全部打包成单个 midas-ch-<UTC ts>.tar.gz → OSS oss://midas-backup-hk/clickhouse/
#
# 用法:
#   - 手动:./scripts/backup_clickhouse.sh
#   - cron(★ Hans 手动试跑验证通过后再挂 · 跟 PG 的 03:00 错峰 30min):
#       30 3 * * *  cd /opt/midas && ./scripts/backup_clickhouse.sh >> /var/log/midas-backup.log 2>&1
#   注意:手动直接跑 ./scripts/backup_clickhouse.sh 时 [backup-ch] 日志只打到屏幕,
#         不会写进 /var/log/midas-backup.log;只有 cron 那行末尾的
#         >> /var/log/midas-backup.log 2>&1 重定向才会落盘。手动跑后用 grep 查日志
#         文件查不到是正常的,不是脚本故障。
#
# 依赖:
#   - docker(用 midas-clickhouse 容器内的 clickhouse-client · 版本天然一致)
#   - ossutil(阿里云 OSS CLI · 与 PG 备份共用)
#   - 凭证:复用 PG 备份的 /etc/midas/backup.env(chmod 600 · root 拥有)· 不新增文件:
#       OSS_ENDPOINT=oss-cn-hongkong-internal.aliyuncs.com
#       OSS_BUCKET=midas-backup-hk
#       OSS_ACCESS_KEY_ID=...
#       OSS_ACCESS_KEY_SECRET=...
#
# 连接:容器内 localhost / default 用户走 native 9000 不校验密码(docs/decisions/0002)·
#       本机现有 4 个脚本已验证 `docker exec midas-clickhouse clickhouse-client --query` 免认证可用。
#
# ────────────────────────────────────────────────────────────────────────────
# 【恢复 runbook】未来运维照此走 · 备份没验证过的恢复 = 没备,务必先试跑过一次:
#   1. 从 OSS 取回 + 解包:
#        ossutil cp oss://midas-backup-hk/clickhouse/midas-ch-<ts>.tar.gz . \
#          --endpoint=oss-cn-hongkong-internal.aliyuncs.com \
#          --access-key-id=... --access-key-secret=...
#        mkdir restore && tar xzf midas-ch-<ts>.tar.gz -C restore && cd restore
#   2. 建表(全新 CH 由 docker/clickhouse-init.sql + worker 启动 ch_schema.py 自动建 ·
#      已存在则跳过;需手动重建某表时):
#        docker exec -i midas-clickhouse clickhouse-client --multiquery < kline.sql
#   3. 逐表灌数据(Native 对称导入 · 注意 -i 喂 stdin):
#        gunzip -c kline.native.gz | docker exec -i midas-clickhouse \
#          clickhouse-client --query "INSERT INTO default.kline FORMAT Native"
#      (ReplacingMergeTree 建议灌进空表最干净 · 重灌按 version 列后台 merge 去重)
#   4. ★ 校验:恢复后行数必须对得上 manifest.txt 记录:
#        docker exec midas-clickhouse clickhouse-client --query "SELECT count() FROM default.kline"
#        grep -P '^kline\t' manifest.txt   # 第 2 列即备份时行数 · 两者相等才算恢复成功
# ────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# === 配置 ===
BACKUP_DIR="${BACKUP_DIR:-/var/backups/midas}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"
CH_CONTAINER="${CH_CONTAINER:-midas-clickhouse}"
CH_DATABASE="${CH_DATABASE:-default}"
OSS_PREFIX="${OSS_PREFIX:-clickhouse}"

# 从安全位置加载凭证(与 PG 备份共用同一个文件 · 避免硬编码)
if [ -f /etc/midas/backup.env ]; then
  # shellcheck disable=SC1091
  source /etc/midas/backup.env
fi

# 检查必要 env(与 PG 版同样四个守卫)
: "${OSS_ENDPOINT:?未设置 OSS_ENDPOINT}"
: "${OSS_BUCKET:?未设置 OSS_BUCKET}"
: "${OSS_ACCESS_KEY_ID:?未设置 OSS_ACCESS_KEY_ID}"
: "${OSS_ACCESS_KEY_SECRET:?未设置 OSS_ACCESS_KEY_SECRET}"

# === 临时工作目录 + 清理 trap(防半成品的关键)===
# 所有逐表中间产物(.sql/.native.gz/manifest)只落在 WORKDIR;最终 tar.gz 只在
# 全部表导出成功【之后】才生成 → set -e + pipefail 下任一表失败立即退出,绝不会留下
# "半成品" tar.gz 冒充完整备份(此刻只有被 trap 清掉的 WORKDIR,无归档产出)。
# trap 保证无论成败都清掉中间目录;exit $rc 原样透传退出码(EXIT trap 内 exit 不再触发 trap)。
WORKDIR=""
cleanup() {
  rc=$?
  if [ -n "${WORKDIR:-}" ] && [ -d "${WORKDIR:-}" ]; then
    rm -rf "$WORKDIR" 2>/dev/null || true
  fi
  exit "$rc"
}
trap cleanup EXIT

mkdir -p "$BACKUP_DIR"
WORKDIR="$(mktemp -d "${BACKUP_DIR}/ch-work-XXXXXX")"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/midas-ch-${TIMESTAMP}.tar.gz"
MANIFEST="$WORKDIR/manifest.txt"

echo "[backup-ch] $(date -u +%FT%TZ) start · → $BACKUP_FILE"

# === 动态枚举 default 库下所有 MergeTree 系表(新增表自动纳入)===
TABLES="$(docker exec "$CH_CONTAINER" clickhouse-client --query \
  "SELECT name FROM system.tables WHERE database='${CH_DATABASE}' AND engine LIKE '%MergeTree%' ORDER BY name")"

if [ -z "$TABLES" ]; then
  echo "[backup-ch] ERROR · 没枚举到任何表(CH 连不上?库名错?)· 异常退出"
  exit 3
fi

# manifest 表头(# 开头 · 恢复校验时取非 # 行;字段:表名 行数 压缩字节数)
printf '# table\trows\tbytes\n' > "$MANIFEST"

# === 逐表导出:DDL + 数据(Native|gzip) + 行数 ===
TABLE_COUNT=0
TOTAL_ROWS=0
while IFS= read -r t; do
  [ -z "$t" ] && continue

  # ① 建表语句 · TabSeparatedRaw 输出真实换行(可直接 multiquery 恢复;非 Raw 会带 \n 转义无法用)
  docker exec "$CH_CONTAINER" clickhouse-client --query \
    "SHOW CREATE TABLE ${CH_DATABASE}.${t} FORMAT TabSeparatedRaw" > "$WORKDIR/${t}.sql"

  # ② 数据 · Native 二进制零损 · pipefail 保证 docker exec 失败时整条管道失败(不被 gzip 的成功吞掉)
  docker exec "$CH_CONTAINER" clickhouse-client --query \
    "SELECT * FROM ${CH_DATABASE}.${t} FORMAT Native" | gzip -9 > "$WORKDIR/${t}.native.gz"

  # ③ 行数 + 压缩字节数 → manifest(恢复时按行数对账)
  rows="$(docker exec "$CH_CONTAINER" clickhouse-client --query \
    "SELECT count() FROM ${CH_DATABASE}.${t}")"
  bytes="$(stat -c%s "$WORKDIR/${t}.native.gz" 2>/dev/null || stat -f%z "$WORKDIR/${t}.native.gz")"
  printf '%s\t%s\t%s\n' "$t" "$rows" "$bytes" >> "$MANIFEST"

  TABLE_COUNT=$((TABLE_COUNT + 1))
  TOTAL_ROWS=$((TOTAL_ROWS + rows))
  echo "[backup-ch] dumped ${t} · ${rows} rows · $(du -h "$WORKDIR/${t}.native.gz" | cut -f1)"
done <<< "$TABLES"

echo "[backup-ch] 导出完成 · ${TABLE_COUNT} 表 · 合计 ${TOTAL_ROWS} 行"

# === 打包成单个 tar.gz(含 manifest + 各表 .sql + .native.gz · 归档内路径相对)===
tar -czf "$BACKUP_FILE" -C "$WORKDIR" .

# 大小校验(< 1KB 视为失败 · 照 PG 版逻辑)
SIZE_BYTES="$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE")"
if [ "$SIZE_BYTES" -lt 1024 ]; then
  echo "[backup-ch] ERROR · 归档 < 1KB · 异常退出"
  rm -f "$BACKUP_FILE"
  exit 2
fi
echo "[backup-ch] archive OK · $(du -h "$BACKUP_FILE" | cut -f1)"

# === 上传 OSS(香港内网 endpoint · 免流量费)===
OSS_KEY="${OSS_PREFIX}/$(basename "$BACKUP_FILE")"
ossutil cp "$BACKUP_FILE" "oss://${OSS_BUCKET}/${OSS_KEY}" \
  --endpoint="$OSS_ENDPOINT" \
  --access-key-id="$OSS_ACCESS_KEY_ID" \
  --access-key-secret="$OSS_ACCESS_KEY_SECRET" \
  -f
echo "[backup-ch] uploaded → oss://${OSS_BUCKET}/${OSS_KEY}"

# === 清本地超过 RETAIN_DAYS 天的旧备份 ===
find "$BACKUP_DIR" -name "midas-ch-*.tar.gz" -mtime "+${RETAIN_DAYS}" -delete
echo "[backup-ch] local cleanup · 保留近 ${RETAIN_DAYS} 天"

# OSS 端保留由桶生命周期规则负责(clickhouse/ 7d、postgres/ 30d);脚本不再删 OSS。

echo "[backup-ch] $(date -u +%FT%TZ) done"
