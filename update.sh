#!/bin/bash
# 点金 Midas · 一键更新脚本
# 2026-05-21 · 模式 B 全栈
#
# 用法(服务器):
#   cd /opt/midas
#   bash update.sh
#
# 行为:
#   1. git pull(用 credential.helper store · 不弹 PAT)
#   2. 对比 HEAD 前后差异 · 决定要不要 rebuild + 哪些服务
#   3. 智能动作:
#        · apps/api / apps/worker 改了 → 重建 api + worker
#        · apps/web / packages 改了 → 重建 web
#        · docker/*.yaml 改了 → docker compose up -d --build(全栈影响)
#        · deploy/Caddyfile 改了 → cp + systemctl reload caddy
#        · apps/api/alembic/versions/ 新增 → docker exec midas-api alembic upgrade head
#        · 只是 docs / scripts 改了 → 不做任何动作
#   4. 健康检查 · 5 服务 healthy + worker running
#   5. 打印最终状态
#
# 设计:幂等 · 安全 · 一句话搞定所有迭代部署。

set -euo pipefail

RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; MAGENTA=$'\033[1;35m'; NC=$'\033[0m'

STAGE="init"
on_err() {
  local line=$1
  echo ""
  echo "${RED}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${RED}║  ❌ update.sh 失败 · 阶段=「${STAGE}」 · 行号=${line}${NC}"
  echo "${RED}╚═══════════════════════════════════════════════════════════${NC}"
  echo ""
  echo "${YELLOW}--- docker compose ps 快照 ---${NC}"
  docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted ps 2>/dev/null || true
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
section() { echo ""; echo "${MAGENTA}▸ $1${NC}"; }
ok()      { echo "${GREEN}  ✓ $1${NC}"; }
warn()    { echo "${YELLOW}  ⚠ $1${NC}"; }
skip()    { echo "${YELLOW}  ⊘ $1${NC}"; }

if [ ! -d /opt/midas/.git ]; then
  echo "${RED}❌ /opt/midas 不是 git 仓库 · 在错误的目录运行${NC}"; exit 1
fi
cd /opt/midas

COMPOSE="docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted"
START_TIME=$(date +%s)

# ============================================================
banner "1/6 · git pull · 拉最新代码"
# ============================================================
OLD_HEAD=$(git rev-parse HEAD)
echo "  当前 HEAD = $(git rev-parse --short HEAD)"
git fetch origin main 2>&1 | tail -3
NEW_HEAD=$(git rev-parse origin/main)

if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
  echo ""
  echo "${GREEN}已是最新版本 · HEAD = $(git rev-parse --short HEAD)${NC}"
  echo ""
  echo "${CYAN}─── 顺便健康检查一遍 ───${NC}"
  $COMPOSE ps
  curl -sS http://127.0.0.1:8000/health && echo ""
  echo ""
  echo "${GREEN}✅ 无需更新 · 全栈正常${NC}"
  exit 0
fi

git reset --hard origin/main 2>&1 | tail -1
NEW_HEAD_SHORT=$(git rev-parse --short HEAD)
ok "更新到 HEAD = ${NEW_HEAD_SHORT}"

echo ""
echo "${CYAN}─── 本次更新的 commit ───${NC}"
git log --oneline "${OLD_HEAD}..${NEW_HEAD}" | head -20

# ============================================================
banner "2/6 · 计算变更范围 · 决定需要做什么"
# ============================================================
CHANGED=$(git diff --name-only "${OLD_HEAD}" "${NEW_HEAD}")
TOTAL_FILES=$(echo "$CHANGED" | grep -c "" || true)
echo "  本次变更 ${TOTAL_FILES} 个文件"
echo ""

# 各类别 flag
NEED_BUILD_API=false
NEED_BUILD_WEB=false
NEED_COMPOSE_UP=false
NEED_CADDY_RELOAD=false
NEED_ALEMBIC=false

# api / worker 共用一个 Dockerfile 体系(worker context 是仓库根 · COPY apps/api + apps/worker)
if echo "$CHANGED" | grep -qE "^apps/api/|^apps/worker/"; then
  NEED_BUILD_API=true
  echo "  ${MAGENTA}▸${NC} 检测到 apps/api/ 或 apps/worker/ 改动 → 重建 api + worker"
fi

# web 的 build context 是仓库根 · 也覆盖 packages/shared
if echo "$CHANGED" | grep -qE "^apps/web/|^packages/"; then
  NEED_BUILD_WEB=true
  echo "  ${MAGENTA}▸${NC} 检测到 apps/web/ 或 packages/ 改动 → 重建 web"
fi

# compose 文件本身改了 → 用 compose up 来 apply
if echo "$CHANGED" | grep -qE "^docker/docker-compose.*\.yaml$"; then
  NEED_COMPOSE_UP=true
  echo "  ${MAGENTA}▸${NC} 检测到 compose yaml 改动 → docker compose up -d(配置 apply)"
fi

# Caddyfile 改了
if echo "$CHANGED" | grep -q "^deploy/Caddyfile$"; then
  NEED_CADDY_RELOAD=true
  echo "  ${MAGENTA}▸${NC} 检测到 deploy/Caddyfile 改动 → 更新 /etc/caddy/Caddyfile + reload"
fi

# alembic migration 新增(只看新文件 · 不看修改)
NEW_MIGRATIONS=$(git diff --name-only --diff-filter=A "${OLD_HEAD}" "${NEW_HEAD}" | grep "^apps/api/alembic/versions/.*\.py$" || true)
if [ -n "$NEW_MIGRATIONS" ]; then
  NEED_ALEMBIC=true
  echo "  ${MAGENTA}▸${NC} 检测到新 migration:$(echo "$NEW_MIGRATIONS" | tr '\n' ' ')"
  echo "    → 跑 alembic upgrade head"
fi

# 如果 api 或 web 要重 build · 一并触发 compose up
if [ "$NEED_BUILD_API" = "true" ] || [ "$NEED_BUILD_WEB" = "true" ]; then
  NEED_COMPOSE_UP=true
fi

if [ "$NEED_BUILD_API" = "false" ] && [ "$NEED_BUILD_WEB" = "false" ] \
   && [ "$NEED_COMPOSE_UP" = "false" ] && [ "$NEED_CADDY_RELOAD" = "false" ] \
   && [ "$NEED_ALEMBIC" = "false" ]; then
  ok "本次变更只涉及 docs/scripts/ADR · 无需重建任何容器"
fi

# ============================================================
banner "3/6 · 执行 docker 层动作"
# ============================================================
# 收集"有代码改动、需要强制重建"的【无状态】服务(只 api/worker/web)。
# ⚠ 安全边界:postgres / clickhouse / redis 是有状态服务,绝不放进这个列表、绝不 --force-recreate、绝不动数据卷。
RECREATE_SVCS=()
[ "$NEED_BUILD_API" = "true" ] && RECREATE_SVCS+=("api" "worker")
[ "$NEED_BUILD_WEB" = "true" ] && RECREATE_SVCS+=("web")

if [ ${#RECREATE_SVCS[@]} -gt 0 ]; then
  section "强制重建有代码改动的无状态服务:${RECREATE_SVCS[*]}"
  # --build         重建镜像
  # --force-recreate 即使 Docker 层缓存命中、镜像未变,也用新镜像重建容器
  #                  → 根治"代码已在 main / 已在主机磁盘,但运行容器还是旧码"(2026-05-27 故障)
  # --no-deps       只动列出的无状态服务,绝不触碰它们的依赖(postgres/clickhouse/redis 不重建、数据卷不动)
  $COMPOSE up -d --build --force-recreate --no-deps "${RECREATE_SVCS[@]}" 2>&1 | tail -40
  ok "force-recreate 完成:${RECREATE_SVCS[*]}(有状态容器未触碰)"
elif [ "$NEED_COMPOSE_UP" = "true" ]; then
  # 仅 compose yaml 改动(无后端/前端代码改动)→ 普通 up -d 应用配置差异。
  # 不 --build、不 --force-recreate:compose 只重建"配置确实变了"的服务,有状态容器不会被无故重建。
  section "compose 配置变更 · docker compose up -d 应用(不 --build / 不 --force-recreate)"
  $COMPOSE up -d 2>&1 | tail -40
  ok "compose up 返回"
else
  skip "docker 容器无需变更"
fi

# ============================================================
banner "4/6 · alembic migration(如有新文件)"
# ============================================================
if [ "$NEED_ALEMBIC" = "true" ]; then
  section "等 api 容器健康再跑 alembic upgrade head"
  for try in $(seq 1 12); do
    state=$(docker inspect -f '{{.State.Health.Status}}' midas-api 2>/dev/null || echo "no-container")
    if [ "$state" = "healthy" ]; then break; fi
    echo "  [try $try/12] api state = $state · 等 10s..."
    sleep 10
  done
  docker exec midas-api alembic upgrade head 2>&1 | tail -10
  ALEMBIC_CUR=$(docker exec midas-api alembic current 2>&1 | grep -v "^INFO\|^$" | tail -1)
  ok "alembic current: $ALEMBIC_CUR"
else
  skip "没有新 migration"
fi

# ============================================================
banner "5/6 · Caddy 配置 reload(如有改动)"
# ============================================================
if [ "$NEED_CADDY_RELOAD" = "true" ]; then
  section "cp deploy/Caddyfile + caddy validate + systemctl reload"
  cp /opt/midas/deploy/Caddyfile /etc/caddy/Caddyfile
  caddy validate --config /etc/caddy/Caddyfile 2>&1
  systemctl reload caddy 2>&1 || systemctl restart caddy
  ok "Caddy reload 完成"
else
  skip "Caddyfile 没变 · 不动 caddy"
fi

# ============================================================
banner "6/6 · 健康检查 + 汇总"
# ============================================================
STAGE="6/6 healthcheck"

# 等服务回到 healthy(如果有重建 · 给 90s)
if [ "$NEED_COMPOSE_UP" = "true" ]; then
  echo "  等 5 服务 healthy + worker running(最多 90s)..."
  HEALTHCHECK=("midas-postgres" "midas-clickhouse" "midas-redis" "midas-api" "midas-web")
  for try in $(seq 1 9); do
    all_healthy=true
    for svc in "${HEALTHCHECK[@]}"; do
      state=$(docker inspect -f '{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "no-container")
      [ "$state" = "healthy" ] || all_healthy=false
    done
    worker_state=$(docker inspect -f '{{.State.Status}}' midas-worker 2>/dev/null || echo "?")
    [ "$worker_state" = "running" ] || all_healthy=false
    if [ "$all_healthy" = "true" ]; then break; fi
    echo "  [try $try/9 @ $(date +%T)] 等服务回 healthy..."
    sleep 10
  done
fi

echo ""
echo "${CYAN}─── docker compose ps ───${NC}"
$COMPOSE ps

echo ""
echo "${CYAN}─── /health + web HEAD ───${NC}"
curl -sS http://127.0.0.1:8000/health || warn "/health 不通"
echo ""
curl -sI http://127.0.0.1:3000/ | head -3

echo ""
echo "${CYAN}─── HTTPS 三域名 ───${NC}"
printf "  api  · "; curl -sS -o /dev/null -w "HTTP %{http_code} · %{time_total}s\n" --max-time 10 "https://api.midastrade.asia/health" || true
printf "  main · "; curl -sS -o /dev/null -w "HTTP %{http_code} · %{time_total}s\n" --max-time 10 "https://midastrade.asia/" || true
printf "  www  · "; curl -sS -o /dev/null -w "HTTP %{http_code} · %{time_total}s\n" --max-time 10 -L "https://www.midastrade.asia/" || true

ELAPSED=$(($(date +%s) - START_TIME))

echo ""
echo "${GREEN}╔═══════════════════════════════════════════════════════════${NC}"
echo "${GREEN}║  ✅ update.sh 完成 · 用时 ${ELAPSED}s${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  本次变更摘要:${NC}"
[ "$NEED_BUILD_API"   = "true" ] && echo "${GREEN}║    · 重建了 api + worker${NC}"
[ "$NEED_BUILD_WEB"   = "true" ] && echo "${GREEN}║    · 重建了 web${NC}"
[ "$NEED_COMPOSE_UP"  = "true" ] && echo "${GREEN}║    · docker compose up -d apply${NC}"
[ "$NEED_ALEMBIC"     = "true" ] && echo "${GREEN}║    · alembic 升级到 head${NC}"
[ "$NEED_CADDY_RELOAD" = "true" ] && echo "${GREEN}║    · caddy 配置 reload${NC}"
[ "$NEED_BUILD_API"   = "false" ] && [ "$NEED_BUILD_WEB" = "false" ] \
  && [ "$NEED_COMPOSE_UP" = "false" ] && [ "$NEED_CADDY_RELOAD" = "false" ] \
  && [ "$NEED_ALEMBIC" = "false" ] \
  && echo "${GREEN}║    · 只是 docs/scripts 改动 · 容器没动${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  HEAD = ${NEW_HEAD_SHORT}${NC}"
echo "${GREEN}╚═══════════════════════════════════════════════════════════${NC}"
