#!/bin/bash
# 点金 Midas · Worker OOM 修复后收尾脚本(0015 ADR)
# 不动 api/web/数据库 · 只重建 worker · 等稳定 · 补跑数据预热
#
# 使用:
#   cd /opt/midas
#   git pull origin main
#   bash scripts/deploy-worker-fix.sh 2>&1 | tee /tmp/worker-fix.log

set -euo pipefail

RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; NC=$'\033[0m'
STAGE="init"
on_err() {
  local line=$1
  echo ""
  echo "${RED}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${RED}║  ❌ 失败 · 阶段=「${STAGE}」 · 行号=${line}${NC}"
  echo "${RED}╚═══════════════════════════════════════════════════════════${NC}"
  echo ""
  echo "${YELLOW}--- midas-worker 最后 50 行 ---${NC}"
  docker logs midas-worker 2>&1 | tail -50 || true
  echo "${YELLOW}--- worker inspect 关键字段 ---${NC}"
  docker inspect midas-worker --format \
    '  State: {{.State.Status}}  ExitCode: {{.State.ExitCode}}  RestartCount: {{.RestartCount}}  OOMKilled: {{.State.OOMKilled}}' 2>/dev/null || true
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
ok() { echo "${GREEN}  ✓ $1${NC}"; }
warn() { echo "${YELLOW}  ⚠ $1${NC}"; }

if [ ! -d /opt/midas/.git ]; then
  echo "${RED}❌ /opt/midas 不是 git 仓库${NC}"; exit 1
fi
cd /opt/midas

COMPOSE="docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted"

# ============================================================
banner "1/6 · 自检 · compose prod.yaml 含 --concurrency=2"
# ============================================================
# 不依赖具体 commit hash · 直接检查文件内容
if ! grep -q -- "--concurrency=2" docker/docker-compose.prod.yaml 2>/dev/null; then
  echo "${RED}❌ docker/docker-compose.prod.yaml 没有 --concurrency=2${NC}"
  echo "${YELLOW}请先在 /opt/midas 跑 git pull origin main · 然后重跑${NC}"
  exit 1
fi
# 内存限额也应该是 1G (而不是 512M)
if grep -A20 "^  worker:" docker/docker-compose.prod.yaml | grep -q "memory: 512M"; then
  echo "${RED}❌ worker memory 还是 512M · 0015 修复未完整 pull 下来${NC}"
  exit 1
fi
HEAD_HASH=$(git rev-parse --short HEAD)
ok "HEAD = $HEAD_HASH · prod.yaml 含 --concurrency=2 + memory: 1G"

# ============================================================
banner "2/6 · force-recreate worker · 不动其他服务"
# ============================================================
# --no-deps 跳过 depends_on · 只动 worker 本身
$COMPOSE up -d --no-deps --force-recreate worker 2>&1 | tail -10
ok "worker 重建命令返回 · 等稳定"
sleep 3

# ============================================================
banner "3/6 · 等 worker 稳定 · RestartCount 30s 不再涨"
# ============================================================
LAST_COUNT=""
STABLE_TICKS=0
for try in $(seq 1 20); do
  STATE=$(docker inspect -f '{{.State.Status}}' midas-worker 2>/dev/null || echo "no-container")
  COUNT=$(docker inspect -f '{{.RestartCount}}' midas-worker 2>/dev/null || echo "0")
  EXIT_CODE=$(docker inspect -f '{{.State.ExitCode}}' midas-worker 2>/dev/null || echo "?")
  OOM=$(docker inspect -f '{{.State.OOMKilled}}' midas-worker 2>/dev/null || echo "?")
  echo "  [try $try/20 @ $(date +%T)] status=$STATE  exit=$EXIT_CODE  restart_count=$COUNT  oom=$OOM  stable_ticks=$STABLE_TICKS"

  if [ "$STATE" = "running" ] && [ "$COUNT" = "$LAST_COUNT" ]; then
    STABLE_TICKS=$((STABLE_TICKS + 1))
  else
    STABLE_TICKS=0
  fi
  LAST_COUNT=$COUNT

  if [ "$STABLE_TICKS" -ge 3 ]; then  # 3 × 10s = 30s
    ok "worker 稳定 running 30+ 秒 · RestartCount = $COUNT(不再涨)"
    break
  fi

  if [ "$try" = "20" ]; then
    echo "${RED}  ❌ 200s 内 worker 未稳定 · 还在重启${NC}"
    docker logs midas-worker 2>&1 | tail -60
    exit 1
  fi
  sleep 10
done

# ============================================================
banner "4/6 · worker 资源占用 + Celery ready 日志"
# ============================================================
docker stats midas-worker --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
echo ""
echo "${CYAN}  --- worker celery ready 日志 ---${NC}"
docker logs midas-worker 2>&1 | grep -E "ready\.|mingle|MainProcess|concurrency" | tail -10

# ============================================================
banner "5/6 · 补跑 STEP 12 数据预热 · 3 标的 × 4 周期"
# ============================================================
warn "可能 3-5 min · 上游限流时部分周期 fail · 不阻塞"
set +e
docker exec midas-worker python -m tasks.data_ingest --all-periods 2>&1 | tail -60
BACKFILL_RC=$?
set -e
if [ "$BACKFILL_RC" != "0" ]; then
  warn "回填脚本退出码 $BACKFILL_RC · 部分周期可能失败 · 继续"
fi

echo ""
echo "${CYAN}  --- ClickHouse 实际数据行数 ---${NC}"
docker exec midas-clickhouse clickhouse-client --query "
SELECT market, symbol, period, count() AS rows, max(ts) AS latest
FROM kline
GROUP BY market, symbol, period
ORDER BY market, symbol, period
FORMAT PrettyCompactMonoBlock
" 2>&1 | head -40

# ============================================================
banner "6/6 · 最终汇总 · 全栈状态"
# ============================================================
STAGE="6/6 final summary"

echo "${CYAN}─── docker compose ps ───${NC}"
$COMPOSE ps

echo ""
echo "${CYAN}─── curl /health ───${NC}"
curl -sS http://127.0.0.1:8000/health
echo ""

echo ""
echo "${CYAN}─── curl /api/v1/market/kline?symbol=NVDA&market=us&period=1d&limit=3 ───${NC}"
curl -sS "http://127.0.0.1:8000/api/v1/market/kline?symbol=NVDA&market=us&period=1d&limit=3" 2>&1 | head -c 400
echo ""

echo ""
echo "${CYAN}─── curl web 首页 (HEAD) ───${NC}"
curl -sI http://127.0.0.1:3000/ | head -5 || warn "web 不通"

echo ""
echo "${CYAN}─── 全栈资源占用 ───${NC}"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep midas

echo ""
echo "${GREEN}╔═══════════════════════════════════════════════════════════${NC}"
echo "${GREEN}║  ✅ worker OOM 修复 + STEP 12 数据预热完成(0015)${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  STEP 10 + 11 + 12 全部完成${NC}"
echo "${GREEN}║  下一步:STEP 13 · Caddyfile + HTTPS 自动证书${NC}"
echo "${GREEN}╚═══════════════════════════════════════════════════════════${NC}"
