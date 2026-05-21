#!/bin/bash
# 点金 Midas · Postgres 每日备份 → 阿里云 OSS 香港
# 0006 / 部署 ADR · 2026-05-21 产品负责人指令:每日 pg_dump → OSS 香港 → 保留 7 天
#
# 用法:
#   - 手动:./scripts/backup_postgres.sh
#   - cron:0 3 * * *  cd /opt/midas && ./scripts/backup_postgres.sh >> /var/log/midas-backup.log 2>&1
#
# 依赖:
#   - docker(用 midas-postgres 容器内的 pg_dump,版本一致)
#   - ossutil(阿里云 OSS CLI · https://help.aliyun.com/zh/oss/developer-reference/ossutil)
#   - 环境变量(放在 /etc/midas/backup.env · chmod 600 · root 拥有):
#       OSS_ENDPOINT=oss-cn-hongkong-internal.aliyuncs.com
#       OSS_BUCKET=midas-backup-hk
#       OSS_ACCESS_KEY_ID=...
#       OSS_ACCESS_KEY_SECRET=...

set -euo pipefail

# === 配置 ===
BACKUP_DIR="${BACKUP_DIR:-/var/backups/midas}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"
PG_CONTAINER="${PG_CONTAINER:-midas-postgres}"
PG_USER="${PG_USER:-midas}"
PG_DB="${PG_DB:-midas}"
OSS_PREFIX="${OSS_PREFIX:-postgres}"

# 从安全位置加载凭证(避免硬编码)
if [ -f /etc/midas/backup.env ]; then
  # shellcheck disable=SC1091
  source /etc/midas/backup.env
fi

# 检查必要 env
: "${OSS_ENDPOINT:?未设置 OSS_ENDPOINT}"
: "${OSS_BUCKET:?未设置 OSS_BUCKET}"
: "${OSS_ACCESS_KEY_ID:?未设置 OSS_ACCESS_KEY_ID}"
: "${OSS_ACCESS_KEY_SECRET:?未设置 OSS_ACCESS_KEY_SECRET}"

# === 准备 ===
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_FILE="$BACKUP_DIR/midas-pg-${TIMESTAMP}.sql.gz"

echo "[backup] $(date -u +%FT%TZ) start · → $BACKUP_FILE"

# === pg_dump · 走 docker 容器内的 pg_dump 跟 server 版本一致 ===
docker exec -i "$PG_CONTAINER" pg_dump \
  -U "$PG_USER" -d "$PG_DB" \
  --no-owner --no-acl \
  --format=plain \
  | gzip -9 > "$BACKUP_FILE"

# 大小校验(< 1KB 视为失败)
SIZE_BYTES=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE")
if [ "$SIZE_BYTES" -lt 1024 ]; then
  echo "[backup] ERROR · dump 文件 < 1KB · 异常退出"
  rm -f "$BACKUP_FILE"
  exit 2
fi
echo "[backup] dump OK · $(du -h "$BACKUP_FILE" | cut -f1)"

# === 上传 OSS(香港内网 endpoint · 免流量费)===
OSS_KEY="${OSS_PREFIX}/$(basename "$BACKUP_FILE")"
ossutil cp "$BACKUP_FILE" "oss://${OSS_BUCKET}/${OSS_KEY}" \
  --endpoint="$OSS_ENDPOINT" \
  --access-key-id="$OSS_ACCESS_KEY_ID" \
  --access-key-secret="$OSS_ACCESS_KEY_SECRET" \
  -f
echo "[backup] uploaded → oss://${OSS_BUCKET}/${OSS_KEY}"

# === 清本地超过 RETAIN_DAYS 天的旧备份 ===
find "$BACKUP_DIR" -name "midas-pg-*.sql.gz" -mtime "+${RETAIN_DAYS}" -delete
echo "[backup] local cleanup · 保留近 ${RETAIN_DAYS} 天"

# === 清 OSS 上 RETAIN_DAYS 天前的旧备份 ===
# OSS 用 lifecycle rule 更稳(走平台规则 · 不依赖脚本) ·
# 这里只做 fallback:列出 < retain 天的文件之外的删除
CUTOFF_DATE=$(date -u -d "-${RETAIN_DAYS} days" +%Y%m%d 2>/dev/null || date -u -v "-${RETAIN_DAYS}d" +%Y%m%d)
ossutil ls "oss://${OSS_BUCKET}/${OSS_PREFIX}/" \
  --endpoint="$OSS_ENDPOINT" \
  --access-key-id="$OSS_ACCESS_KEY_ID" \
  --access-key-secret="$OSS_ACCESS_KEY_SECRET" \
  -s | awk '{print $NF}' | grep -E "midas-pg-[0-9]{8}T" \
  | while read -r key; do
    file_date=$(echo "$key" | sed -E 's/.*midas-pg-([0-9]{8})T.*/\1/')
    if [ -n "$file_date" ] && [ "$file_date" -lt "$CUTOFF_DATE" ]; then
      echo "[backup] OSS expire · rm $key"
      ossutil rm "$key" \
        --endpoint="$OSS_ENDPOINT" \
        --access-key-id="$OSS_ACCESS_KEY_ID" \
        --access-key-secret="$OSS_ACCESS_KEY_SECRET" \
        -f -b
    fi
  done

echo "[backup] $(date -u +%FT%TZ) done"
