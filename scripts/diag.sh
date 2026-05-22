#!/bin/bash
# 点金 Midas · 一键诊断脚本
# 卡住时只跑这一条 · 一次性输出全部排查信息 · 贴一次给 Claude 拿全貌
#
# 用法(服务器):
#   cd /opt/midas && bash scripts/diag.sh 2>&1 | tee /tmp/midas-diag.log
#   然后把终端输出(或 /tmp/midas-diag.log)整段贴回
#
# 设计:全程只读 · 不改任何状态 · 每段 || true 兜底 · 一段失败不影响其它段。
# 不含任何敏感值(不打印 .env 内容 · 只打印 key 名 + 是否存在)。

# 注意:不用 set -e · 诊断脚本要尽量跑完所有段 · 即使某命令失败

CYAN=$'\033[1;36m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
section() {
  echo ""
  echo "${CYAN}╔══════════════════════════════════════════════════════════════${NC}"
  echo "${CYAN}║  $1${NC}"
  echo "${CYAN}╚══════════════════════════════════════════════════════════════${NC}"
}

COMPOSE="docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted"
CONTAINERS="midas-postgres midas-clickhouse midas-redis midas-api midas-worker midas-web"

echo "════════════════════════════════════════════════════════════════"
echo "  点金 Midas · 一键诊断 · $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "  主机: $(hostname) · 内核: $(uname -r)"
echo "════════════════════════════════════════════════════════════════"

# ============================================================
section "1 · Git 状态(分支 / HEAD / 最近提交 / 是否有未提交改动)"
# ============================================================
cd /opt/midas 2>/dev/null && {
  echo "工作目录: $(pwd)"
  echo "当前分支: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
  echo "HEAD: $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
  echo ""
  echo "── 最近 5 个 commit ──"
  git log --oneline -5 2>/dev/null || echo "(git log 失败)"
  echo ""
  echo "── working tree 状态(应 clean)──"
  git status --short 2>/dev/null || echo "(git status 失败)"
  echo ""
  echo "── 远端同步状态 ──"
  git fetch origin 2>/dev/null
  echo "本地 HEAD: $(git rev-parse --short HEAD 2>/dev/null)"
  echo "origin/main: $(git rev-parse --short origin/main 2>/dev/null || echo '?')"
} || echo "(/opt/midas 不存在或不是 git 仓库)"

# ============================================================
section "2 · docker compose ps(全栈服务状态)"
# ============================================================
cd /opt/midas 2>/dev/null && $COMPOSE ps 2>&1 || docker ps -a --filter "name=midas" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>&1 || echo "(docker 不可用)"

# ============================================================
section "3 · 各容器健康 + 重启次数 + OOM 标记"
# ============================================================
for c in $CONTAINERS; do
  state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "no-container")
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$c" 2>/dev/null || echo "?")
  restarts=$(docker inspect -f '{{.RestartCount}}' "$c" 2>/dev/null || echo "?")
  oom=$(docker inspect -f '{{.State.OOMKilled}}' "$c" 2>/dev/null || echo "?")
  exitcode=$(docker inspect -f '{{.State.ExitCode}}' "$c" 2>/dev/null || echo "?")
  printf "  %-18s status=%-12s health=%-10s restarts=%-3s oom=%-5s exit=%s\n" \
    "$c" "$state" "$health" "$restarts" "$oom" "$exitcode"
done

# ============================================================
section "4 · 各容器最近 50 行日志"
# ============================================================
for c in $CONTAINERS; do
  echo ""
  echo "${YELLOW}──────── $c (最近 50 行)────────${NC}"
  docker logs --tail 50 "$c" 2>&1 || echo "(容器不存在或无日志)"
done

# ============================================================
section "5 · 资源占用(docker stats 快照)"
# ============================================================
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" 2>&1 | grep -E "midas|NAME" || echo "(docker stats 失败)"

# ============================================================
section "6 · 系统内存 + 磁盘"
# ============================================================
echo "── 内存 (free -h) ──"
free -h 2>&1 || echo "(free 不可用)"
echo ""
echo "── 磁盘 (df -h 根分区 + docker)──"
df -h / /var/lib/docker 2>&1 | sort -u || df -h 2>&1 | head -8
echo ""
echo "── docker 磁盘占用 ──"
docker system df 2>&1 || echo "(docker system df 失败)"

# ============================================================
section "7 · 端口监听(80/443/3000/8000/5432/8123/6379)"
# ============================================================
ss -tlnp 2>/dev/null | grep -E ':(80|443|3000|8000|5432|8123|6379)\s' || \
  netstat -tlnp 2>/dev/null | grep -E ':(80|443|3000|8000|5432|8123|6379)\s' || \
  echo "(ss/netstat 不可用)"

# ============================================================
section "8 · Caddy 状态 + 端口"
# ============================================================
systemctl is-active caddy 2>&1 | sed 's/^/  caddy active: /' || echo "(caddy 未装)"
systemctl is-enabled caddy 2>&1 | sed 's/^/  caddy enabled: /' || true
echo "── caddy 最近 20 行 ──"
journalctl -u caddy --no-pager -n 20 2>&1 | tail -20 || echo "(无 caddy 日志)"

# ============================================================
section "9 · 内部健康检查(localhost · 不经公网)"
# ============================================================
echo "── api /health (127.0.0.1:8000)──"
curl -sS --max-time 8 http://127.0.0.1:8000/health 2>&1 || echo "(api 不通)"
echo ""
echo "── web (127.0.0.1:3000)──"
curl -sS -o /dev/null -w "  web HTTP %{http_code}\n" --max-time 8 http://127.0.0.1:3000/ 2>&1 || echo "(web 不通)"

# ============================================================
section "10 · 公网健康检查(经 DNS + Caddy · 外部视角)"
# ============================================================
echo "── https://api.midastrade.asia/health ──"
curl -sS --max-time 12 https://api.midastrade.asia/health 2>&1 || echo "(公网 api 不通)"
echo ""
echo "── https://midastrade.asia/ ──"
curl -sS -o /dev/null -w "  main HTTP %{http_code} · TLS verify=%{ssl_verify_result} · %{time_total}s\n" --max-time 12 https://midastrade.asia/ 2>&1 || echo "(公网 web 不通)"

# ============================================================
section "11 · DNS 解析(三域名应都指 8.210.156.91)"
# ============================================================
for d in midastrade.asia api.midastrade.asia www.midastrade.asia; do
  ip=$(dig +short "$d" @8.8.8.8 2>/dev/null | head -1)
  printf "  %-26s → %s\n" "$d" "${ip:-<解析失败>}"
done

# ============================================================
section "12 · alembic 迁移版本"
# ============================================================
docker exec midas-api alembic current 2>&1 | grep -v "^INFO\|^$" | tail -3 || echo "(api 容器不可用 · 取不到 alembic)"

# ============================================================
section "13 · .env 凭证存在性检查(只看 key 名 · 不打印值)"
# ============================================================
if [ -f /opt/midas/.env ]; then
  echo "  /opt/midas/.env 存在 · 权限 $(stat -c '%a' /opt/midas/.env 2>/dev/null)"
  for k in SECRET_KEY POSTGRES_PASSWORD CLICKHOUSE_PASSWORD DATABASE_URL \
           NEXT_PUBLIC_API_URL API_INTERNAL_URL AUTH_URL AUTH_SECRET \
           GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET RESEND_API_KEY DEEPSEEK_API_KEY; do
    if grep -q "^${k}=" /opt/midas/.env 2>/dev/null; then
      val=$(grep "^${k}=" /opt/midas/.env | head -1 | cut -d= -f2-)
      len=${#val}
      echo "  ✓ ${k} 已设(长度 ${len})"
    else
      echo "  ✗ ${k} 缺失"
    fi
  done
else
  echo "  (/opt/midas/.env 不存在)"
fi
echo ""
echo "  docker/.env symlink(0014 修复 · 应 → ../.env):"
ls -la /opt/midas/docker/.env 2>&1 | sed 's/^/    /' || echo "    (不存在)"

# ============================================================
section "14 · 最近的部署 / 验证日志(/tmp/*.log)"
# ============================================================
for f in /tmp/deploy-step-10-12.log /tmp/worker-fix.log /tmp/deploy-step-13.log \
         /tmp/deploy-step-14.log /tmp/m2a-verify.log /tmp/midas-diag.log; do
  if [ -f "$f" ]; then
    echo "  $f · $(stat -c '%y' "$f" 2>/dev/null | cut -d. -f1) · $(wc -l < "$f") 行 · 末 5 行:"
    tail -5 "$f" 2>&1 | sed 's/^/    /'
    echo ""
  fi
done
echo "  cron 备份日志(/var/log/midas-backup.log 末 5 行):"
tail -5 /var/log/midas-backup.log 2>&1 | sed 's/^/    /' || echo "    (无备份日志)"

# ============================================================
section "诊断完毕"
# ============================================================
echo "  把以上完整输出(或 /tmp/midas-diag.log)整段贴回给 Claude。"
echo "  Claude 能据此一次定位问题 · 不用再来回追问补充信息。"
