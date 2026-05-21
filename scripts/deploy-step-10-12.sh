#!/bin/bash
# 点金 Midas · 部署 STEP 10(0013+0014 修复)+ STEP 11 + STEP 12
# 2026-05-21 · 模式 B 全栈 · 仓库里直接 bash 跑 · 不 heredoc 粘贴
#
# 使用方式(在服务器):
#   cd /opt/midas
#   git pull origin main       ← 必须先 pull · 否则脚本会自检失败并中止
#   bash scripts/deploy-step-10-12.sh 2>&1 | tee /tmp/deploy-step-10-12.log
#
# 为什么脚本里不自己 git pull:
#   脚本自己在仓库里 · git reset --hard 会覆盖正在执行的脚本文件 ·
#   bash 读到一半源文件被换可能行为不确定。所以约定:用户先 pull ·
#   脚本只验证 HEAD 是否到位。

set -euo pipefail

# ============ 期望的最低 HEAD commit(自检用)============
# 这个 commit 包含 0013 ports merge + 0014 DATABASE_URL 双修复
EXPECTED_COMMIT_PREFIX="94faf5a"

# ============ 颜色 + 工具 ============
RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; NC=$'\033[0m'

STAGE="init"
on_err() {
  local line=$1
  echo ""
  echo "${RED}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${RED}║  ❌ 脚本失败 · 阶段=「${STAGE}」 · 行号=${line}${NC}"
  echo "${RED}╚═══════════════════════════════════════════════════════════${NC}"
  echo ""
  echo "${YELLOW}--- docker compose ps(诊断快照)---${NC}"
  docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted ps 2>/dev/null || true
  echo ""
  echo "${YELLOW}--- midas-api 最后 30 行(如果存在)---${NC}"
  docker logs midas-api 2>&1 | tail -30 || true
  echo ""
  echo "${YELLOW}--- midas-postgres 最后 20 行(如果存在)---${NC}"
  docker logs midas-postgres 2>&1 | tail -20 || true
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

# ============ 工作目录守卫 ============
if [ ! -d /opt/midas/.git ]; then
  echo "${RED}❌ /opt/midas 不是 git 仓库 · 请确认 STEP 7 clone 已完成${NC}"
  exit 1
fi
cd /opt/midas

COMPOSE="docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted"

# ============================================================
banner "1/10 · 自检 git HEAD · 必须 >= ${EXPECTED_COMMIT_PREFIX}"
# ============================================================
HEAD_HASH=$(git rev-parse --short HEAD)
echo "  当前 HEAD = ${HEAD_HASH}"
echo ""
echo "${CYAN}  --- 最近 5 个 commit ---${NC}"
git log --oneline -5

# 验证 EXPECTED_COMMIT 是否在历史里
if ! git merge-base --is-ancestor "${EXPECTED_COMMIT_PREFIX}" HEAD 2>/dev/null; then
  echo ""
  echo "${RED}❌ HEAD 没有包含 ${EXPECTED_COMMIT_PREFIX}(0014 DATABASE_URL 修复)${NC}"
  echo "${YELLOW}请先在 /opt/midas 跑 git pull origin main · 然后重跑本脚本${NC}"
  exit 1
fi
ok "HEAD 已包含 ${EXPECTED_COMMIT_PREFIX} · 修复在位"

# ============================================================
banner "2/10 · 建 docker/.env -> ../.env symlink · 让 Compose YAML 插值找到 .env"
# ============================================================
# 0014 ADR · Compose 的 ${VAR} 插值默认在「第一个 -f 文件所在目录」找 .env ·
# 我们 compose 在 docker/ · .env 在 /opt/midas/ · symlink 让插值能找到
if [ -L /opt/midas/docker/.env ]; then
  rm -f /opt/midas/docker/.env
  warn "已有 symlink · 删掉重建确保 target 正确"
fi
if [ -f /opt/midas/docker/.env ] && [ ! -L /opt/midas/docker/.env ]; then
  mv /opt/midas/docker/.env /opt/midas/docker/.env.bak
  warn "/opt/midas/docker/.env 是真文件不是 symlink · 已备份为 .env.bak"
fi
ln -sf ../.env /opt/midas/docker/.env
ls -la /opt/midas/docker/.env
ok "docker/.env -> ../.env symlink 建好"

# ============================================================
banner "3/10 · 验证 compose config · 决定性检查 'midas_dev'"
# ============================================================
CFG=$($COMPOSE config 2>&1)

# 3a: ports MERGE 修复验证(0013)· 用 --format json + jq 避免靠 YAML 缩进数行
# 历史踩坑(deploy run #1):靠 grep "^      - target:" 数 YAML 行 ·
# 实际 compose config YAML 输出的 ports 缩进格式不是「6 空格 + dash」·
# 数到 0 误判 fix 未生效。改用结构化 JSON 解析。
CFG_JSON=$($COMPOSE config --format json 2>/dev/null || echo "{}")
API_PORTS=$(echo "$CFG_JSON" | jq -r '.services.api.ports | length' 2>/dev/null || echo "ERR")
WEB_PORTS=$(echo "$CFG_JSON" | jq -r '.services.web.ports | length' 2>/dev/null || echo "ERR")
# 顺手抽 host_ip(应该是 127.0.0.1)· 任一不是就是 0013 没生效
API_HOST_IP=$(echo "$CFG_JSON" | jq -r '.services.api.ports[0].host_ip // "<missing>"' 2>/dev/null || echo "ERR")
WEB_HOST_IP=$(echo "$CFG_JSON" | jq -r '.services.web.ports[0].host_ip // "<missing>"' 2>/dev/null || echo "ERR")

echo "  API ports 数 = ${API_PORTS} · host_ip = ${API_HOST_IP}"
echo "  WEB ports 数 = ${WEB_PORTS} · host_ip = ${WEB_HOST_IP}"

if [ "$API_PORTS" != "1" ] || [ "$WEB_PORTS" != "1" ]; then
  echo "${RED}  ❌ ports 数不对(应该都是 1)· 0013 fix 未生效${NC}"
  echo "${YELLOW}  --- compose config 里 api/web 的 ports 段落 ---${NC}"
  echo "$CFG_JSON" | jq '.services.api.ports, .services.web.ports' 2>/dev/null || echo "$CFG" | awk '/container_name: midas-(api|web)/,/^  [a-z]/' | head -30
  exit 1
fi

if [ "$API_HOST_IP" != "127.0.0.1" ] || [ "$WEB_HOST_IP" != "127.0.0.1" ]; then
  echo "${RED}  ❌ host_ip 不是 127.0.0.1 · 端口对外暴露 · 0013 修复异常${NC}"
  exit 1
fi
ok "0013 ports merge 修复在位 · api/web 各 1 条 ports · 都绑 127.0.0.1"

# 3b: 决定性检查 · 全文件搜 midas_dev · 必须 0 处
echo ""
echo "${CYAN}  --- grep midas_dev(必须 0 处)---${NC}"
MIDASDEV_COUNT=$(echo "$CFG" | grep -c "midas_dev" || true)
echo "  midas_dev 出现次数 = $MIDASDEV_COUNT"
if [ "$MIDASDEV_COUNT" != "0" ]; then
  echo "${RED}  ❌ compose config 里还有 midas_dev · 0014 fix 未生效 · 中止${NC}"
  echo "${YELLOW}  --- 出现位置:---${NC}"
  echo "$CFG" | grep -n "midas_dev" | head -10
  echo ""
  echo "${YELLOW}  检查清单:${NC}"
  echo "${YELLOW}    1. git log --oneline -3 是否含 94faf5a${NC}"
  echo "${YELLOW}    2. ls -la /opt/midas/docker/.env(必须是 symlink → ../.env)${NC}"
  echo "${YELLOW}    3. cat /opt/midas/.env | grep POSTGRES_PASSWORD(必须有真值)${NC}"
  exit 1
fi
ok "compose config 全文无 midas_dev · 0014 fix 已生效"

# 3c: 抽样看 api 的 DATABASE_URL 前 60 字符
echo ""
echo "${CYAN}  --- api 服务的 DATABASE_URL 前 60 字符 ---${NC}"
echo "$CFG" | awk '/container_name: midas-api/,/^[^ ]/' | grep -E "DATABASE_URL:" | head -1 | cut -c1-80 || true

# ============================================================
banner "4/10 · 清场 · 容器 + 被错密码 init 过的数据卷"
# ============================================================
warn "即将删除 midas-postgres-data + midas-clickhouse-data 数据卷"
warn "这些卷被错密码 init 过 · 卷里 user 密码不对 · 必须清掉重 init"
warn "Redis 数据卷保留(只是缓存 · 无 auth · 无影响)"

$COMPOSE down --remove-orphans 2>&1 | tail -10 || true
sleep 2

docker volume rm midas-postgres-data 2>&1 | tail -3 || warn "midas-postgres-data 不存在或已删"
docker volume rm midas-clickhouse-data 2>&1 | tail -3 || warn "midas-clickhouse-data 不存在或已删"

REMAIN=$(docker ps -a --filter "name=midas" --format "{{.Names}}" | wc -l)
if [ "$REMAIN" != "0" ]; then
  warn "残留 $REMAIN 个 midas 容器 · 强制删"
  docker ps -a --filter "name=midas" --format "{{.Names}}" | xargs -r docker rm -f
fi
ok "容器 + postgres/clickhouse 数据卷全清 · 准备真密码重 init"

# ============================================================
banner "5/10 · docker compose up -d · 全栈起飞 · 真密码 init 数据库"
# ============================================================
$COMPOSE up -d 2>&1 | tail -20
sleep 3
ok "compose up 返回 · 进入健康等待"

# ============================================================
banner "6/10 · 等 5 服务 healthy + worker running(最多 5 分钟)"
# ============================================================
HEALTHCHECK=("midas-postgres" "midas-clickhouse" "midas-redis" "midas-api" "midas-web")
WORKER="midas-worker"
MAX_TRIES=30

for try in $(seq 1 $MAX_TRIES); do
  all_healthy=true
  line=""
  for svc in "${HEALTHCHECK[@]}"; do
    state=$(docker inspect -f '{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "no-container")
    line="$line ${svc##midas-}=$state"
    if [ "$state" != "healthy" ]; then all_healthy=false; fi
  done
  worker_state=$(docker inspect -f '{{.State.Status}}' "$WORKER" 2>/dev/null || echo "no-container")
  line="$line worker=$worker_state"
  if [ "$worker_state" != "running" ]; then all_healthy=false; fi

  echo "  [try $try/$MAX_TRIES @ $(date +%T)]$line"
  if [ "$all_healthy" = "true" ]; then
    ok "5 服务 healthy + worker running"
    break
  fi
  if [ "$try" = "$MAX_TRIES" ]; then
    echo "${RED}  ❌ 5 分钟超时${NC}"
    $COMPOSE ps
    echo ""
    echo "${YELLOW}--- api 最后 60 行 ---${NC}"; docker logs midas-api 2>&1 | tail -60
    echo "${YELLOW}--- postgres 最后 30 行 ---${NC}"; docker logs midas-postgres 2>&1 | tail -30
    echo "${YELLOW}--- web 最后 30 行 ---${NC}"; docker logs midas-web 2>&1 | tail -30
    exit 1
  fi
  sleep 10
done

# ============================================================
banner "7/10 · 二次确认 · 容器内实际 DATABASE_URL 不含 midas_dev"
# ============================================================
echo "${CYAN}  --- midas-api 容器内 DATABASE_URL 前 50 字符 ---${NC}"
API_DB_URL=$(docker exec midas-api printenv DATABASE_URL 2>&1)
echo "  ${API_DB_URL:0:50}..."
if echo "$API_DB_URL" | grep -q "midas_dev"; then
  echo "${RED}  ❌ api 容器 DATABASE_URL 还是 midas_dev · 修复未完整生效${NC}"
  exit 1
fi
ok "api 容器 DATABASE_URL 不含 midas_dev · env_file 真值已生效"

# ============================================================
banner "8/10 · STEP 11 · alembic upgrade head"
# ============================================================
docker exec midas-api alembic upgrade head 2>&1
echo ""
ALEMBIC_CUR=$(docker exec midas-api alembic current 2>&1 | grep -v "^INFO\|^$" | tail -1)
ok "alembic current: ${ALEMBIC_CUR}"
if echo "$ALEMBIC_CUR" | grep -q "d8e2f4a5c7b9"; then
  ok "alembic head = d8e2f4a5c7b9 (Google OAuth)"
else
  warn "alembic head 不是预期的 d8e2f4a5c7b9 · 远端可能有新 migration · 不阻塞"
fi

# ============================================================
banner "9/10 · STEP 12 · 数据预热 · 3 标的 × 4 周期"
# ============================================================
warn "可能耗时 3-5 min · 上游限流时部分周期 fail · 不阻塞"
set +e
docker exec midas-worker python -m tasks.data_ingest --all-periods 2>&1 | tail -50
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
banner "10/10 · 最终状态汇总"
# ============================================================
STAGE="10/10 final summary"

echo "${CYAN}─── docker compose ps ───${NC}"
$COMPOSE ps

echo ""
echo "${CYAN}─── PORTS(应该只见 127.0.0.1 绑定)───${NC}"
$COMPOSE ps --format "table {{.Name}}\t{{.Ports}}" | grep -E "midas-(api|web)" || true

echo ""
echo "${CYAN}─── curl http://127.0.0.1:8000/health ───${NC}"
curl -sS http://127.0.0.1:8000/health || warn "/health 不通"
echo ""

echo ""
echo "${CYAN}─── curl /api/v1/market/kline?symbol=NVDA&market=us&period=1d&limit=3 ───${NC}"
curl -sS "http://127.0.0.1:8000/api/v1/market/kline?symbol=NVDA&market=us&period=1d&limit=3" 2>&1 | head -c 400
echo ""

echo ""
echo "${CYAN}─── curl http://127.0.0.1:3000/ (web 首页 HEAD)───${NC}"
curl -sI http://127.0.0.1:3000/ | head -8 || warn "web 不通"

echo ""
echo "${CYAN}─── docker stats(资源占用)───${NC}"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep midas

echo ""
echo "${CYAN}─── worker celery ready 日志 ───${NC}"
docker logs midas-worker 2>&1 | grep -E "ready\.|mingle|MainProcess" | tail -5

echo ""
echo "${GREEN}╔═══════════════════════════════════════════════════════════${NC}"
echo "${GREEN}║  ✅ STEP 10(0013+0014 修复)+ STEP 11 + STEP 12 完成${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  下一步:STEP 13 · 配 Caddyfile + HTTPS 自动证书${NC}"
echo "${GREEN}║          → https://api.midastrade.asia/health 应该跑通${NC}"
echo "${GREEN}╚═══════════════════════════════════════════════════════════${NC}"
