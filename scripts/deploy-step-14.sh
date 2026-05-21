#!/bin/bash
# 点金 Midas · 部署 STEP 14 · cron 每日 03:00 自动备份 Postgres → OSS
# 2026-05-21 · 模式 B 全栈
#
# 用法(服务器):
#   cd /opt/midas
#   git pull
#   bash scripts/deploy-step-14.sh 2>&1 | tee /tmp/deploy-step-14.log

set -euo pipefail

RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; NC=$'\033[0m'

STAGE="init"
on_err() {
  local line=$1
  echo ""
  echo "${RED}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${RED}║  ❌ 失败 · 阶段=「${STAGE}」 · 行号=${line}${NC}"
  echo "${RED}╚═══════════════════════════════════════════════════════════${NC}"
  exit 1
}
trap 'on_err $LINENO' ERR

banner() {
  STAGE="$1"
  echo ""
  echo "${CYAN}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${CYAN}║  === $1 ===${NC}"
  echo "${CYAN}╚═══════════════════════════════════════════════════════════${NC}"
}
ok()   { echo "${GREEN}  ✓ $1${NC}"; }
warn() { echo "${YELLOW}  ⚠ $1${NC}"; }

if [ ! -d /opt/midas/.git ]; then
  echo "${RED}❌ /opt/midas 不是 git 仓库${NC}"; exit 1
fi
cd /opt/midas

BACKUP_SCRIPT="/opt/midas/scripts/backup_postgres.sh"
BACKUP_ENV="/etc/midas/backup.env"
LOG_FILE="/var/log/midas-backup.log"
CRON_LINE="0 3 * * * cd /opt/midas && /opt/midas/scripts/backup_postgres.sh >> ${LOG_FILE} 2>&1"
CRON_MARKER="# midas-postgres-daily-backup"

# ============================================================
banner "1/6 · 前置检查 · backup 脚本 + 凭证 + ossutil + postgres 容器"
# ============================================================
[ -f "$BACKUP_SCRIPT" ] || { echo "${RED}❌ $BACKUP_SCRIPT 不存在${NC}"; exit 1; }
[ -x "$BACKUP_SCRIPT" ] || chmod +x "$BACKUP_SCRIPT"
ok "$BACKUP_SCRIPT 在位 + 可执行"

[ -f "$BACKUP_ENV" ] || { echo "${RED}❌ $BACKUP_ENV 不存在(STEP 9 应建好)${NC}"; exit 1; }
ENV_PERM=$(stat -c "%a" "$BACKUP_ENV")
[ "$ENV_PERM" = "600" ] || warn "$BACKUP_ENV 权限是 $ENV_PERM · 推荐 600"
ok "$BACKUP_ENV 在位(权限 $ENV_PERM)"

# 验证 4 个 key 都设了
MISSING=""
for k in OSS_ENDPOINT OSS_BUCKET OSS_ACCESS_KEY_ID OSS_ACCESS_KEY_SECRET; do
  if ! grep -q "^${k}=" "$BACKUP_ENV"; then
    MISSING="$MISSING $k"
  fi
done
[ -z "$MISSING" ] || { echo "${RED}❌ backup.env 缺 key:${MISSING}${NC}"; exit 1; }
ok "backup.env 4 个 key 都在(OSS_ENDPOINT / OSS_BUCKET / OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET)"

command -v ossutil >/dev/null || { echo "${RED}❌ ossutil 未装(STEP 5)${NC}"; exit 1; }
ok "ossutil = $(ossutil --version 2>&1 | head -1)"

PG_STATE=$(docker inspect -f '{{.State.Health.Status}}' midas-postgres 2>/dev/null || echo "no-container")
[ "$PG_STATE" = "healthy" ] || { echo "${RED}❌ midas-postgres 不是 healthy(当前=$PG_STATE)${NC}"; exit 1; }
ok "midas-postgres healthy"

# ============================================================
banner "2/6 · 准备日志文件 + 备份目录"
# ============================================================
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"
chown root:root "$LOG_FILE"
mkdir -p /var/backups/midas
ls -la "$LOG_FILE" /var/backups/midas
ok "日志文件 $LOG_FILE + /var/backups/midas 准备好"

# ============================================================
banner "3/6 · 手动跑一次 backup_postgres.sh · 烟测全链路"
# ============================================================
warn "可能耗时 30-90s(取决于 DB 大小 · 当前 fresh deploy 应该很快)"
echo "${CYAN}─── backup_postgres.sh 输出 ───${NC}"
bash "$BACKUP_SCRIPT" 2>&1 | tee /tmp/backup-smoke.log
echo ""
if grep -q "uploaded → oss://" /tmp/backup-smoke.log; then
  ok "备份脚本输出含 'uploaded → oss://...' · 上传成功"
else
  echo "${RED}❌ 备份脚本输出没看到 'uploaded → oss://' · 上传失败${NC}"
  exit 1
fi

# ============================================================
banner "4/6 · OSS 端核对 · 文件真在那里"
# ============================================================
# 从 backup.env 取凭证 list 一下
# shellcheck disable=SC1091
set -a; source "$BACKUP_ENV"; set +a
echo "${CYAN}─── oss://${OSS_BUCKET}/postgres/ 列表 ───${NC}"
ossutil ls "oss://${OSS_BUCKET}/postgres/" \
  --endpoint="$OSS_ENDPOINT" \
  --access-key-id="$OSS_ACCESS_KEY_ID" \
  --access-key-secret="$OSS_ACCESS_KEY_SECRET" \
  -s 2>&1 | tee /tmp/oss-list.log

OBJ_COUNT=$(grep -c "midas-pg-" /tmp/oss-list.log || true)
[ "$OBJ_COUNT" -ge 1 ] || { echo "${RED}❌ OSS bucket 没看到任何 midas-pg-*.sql.gz${NC}"; exit 1; }
ok "OSS 端确认 · 至少 ${OBJ_COUNT} 个备份文件在 bucket"

# 不在脚本里漏 secret · unset
unset OSS_ENDPOINT OSS_BUCKET OSS_ACCESS_KEY_ID OSS_ACCESS_KEY_SECRET

# ============================================================
banner "5/6 · 安装 cron 任务(03:00 每日 UTC+8)"
# ============================================================
# 删旧的(幂等)+ 加新的
CURRENT_CRON=$(crontab -l 2>/dev/null || true)
# 删掉所有 midas 相关旧条目
NEW_CRON=$(echo "$CURRENT_CRON" | grep -v "midas-postgres-daily-backup\|backup_postgres.sh" || true)
# 加新条目(带 marker 注释 · 便于以后识别)
NEW_CRON=$(printf "%s\n%s\n%s\n" "$NEW_CRON" "$CRON_MARKER" "$CRON_LINE")
echo "$NEW_CRON" | grep -v "^$" | crontab -

echo "${CYAN}─── 当前 crontab ───${NC}"
crontab -l
ok "cron 任务安装 · 每日 03:00(服务器 timezone)pg_dump → OSS"

# 验证 cron 服务在跑
systemctl is-active cron >/dev/null || systemctl is-active crond >/dev/null || {
  echo "${RED}❌ cron 服务没起(Ubuntu 通常是 cron · 不是 crond)${NC}"
  systemctl enable --now cron 2>&1 | head -5
}
ok "cron 服务 active"

# ============================================================
banner "6/6 · 最终汇总"
# ============================================================
STAGE="6/6 final"

echo "${CYAN}─── crontab(单 user · root)───${NC}"
crontab -l

echo ""
echo "${CYAN}─── 本地备份目录 /var/backups/midas ───${NC}"
ls -lah /var/backups/midas/ 2>/dev/null | head -5

echo ""
echo "${CYAN}─── 日志文件初始化 ${LOG_FILE} ───${NC}"
ls -lah "$LOG_FILE"
echo "  ↑ 03:00 cron 跑完会追加到这里 · 可用 tail -f $LOG_FILE 跟踪"

echo ""
echo "${GREEN}╔═══════════════════════════════════════════════════════════${NC}"
echo "${GREEN}║  ✅ STEP 14 · 每日备份 cron 安装完成${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  下次自动备份:每天 03:00(服务器时区)${NC}"
echo "${GREEN}║  备份位置:oss://midas-backup-hk/postgres/${NC}"
echo "${GREEN}║  保留策略:本地 7 天 + OSS 生命周期 7 天兜底${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  下一步:STEP 15(端到端验收 · 浏览器手动测)${NC}"
echo "${GREEN}║         + STEP 16(监控基线 · docker stats / journalctl)${NC}"
echo "${GREEN}╚═══════════════════════════════════════════════════════════${NC}"
