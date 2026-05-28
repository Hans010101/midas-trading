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
# ── ADR 0029 DP4:外部 FORCE_REBUILD 开关(GitHub Actions inputs / 服务器手动) ──
# true → 跳 "已是最新" + 跳 diff 判定 · 强制重建 api+worker+web(用于 cache 卡脏 / 强制刷依赖)
# 缺省 false · 不影响正常 push 部署
FORCE_REBUILD="${FORCE_REBUILD:-false}"
# ── ADR 0029 DP2:失败时回滚 git HEAD · 仅在 1/7 真实 reset 后才被赋值 ──
# 防止 "git HEAD 已动 / docker image 未起 / DB 半 migrate" 三向脱钩
OLD_HEAD_SAVED=""

on_err() {
  # ⚠ trap - ERR:进入失败处理后立即解绑 · 防止 trap 内的诊断/回滚命令出错重入触发递归
  trap - ERR
  local line=$1
  echo ""
  echo "${RED}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${RED}║  ❌ update.sh 失败 · 阶段=「${STAGE}」 · 行号=${line}${NC}"
  echo "${RED}╚═══════════════════════════════════════════════════════════${NC}"

  # ── DP2 静默护栏:失败诊断快照(磁盘 · BuildKit · 容器 · 进程) ──
  echo ""
  echo "${YELLOW}--- 磁盘:/var/lib/docker ---${NC}"
  df -h /var/lib/docker 2>/dev/null || true
  echo ""
  echo "${YELLOW}--- docker system df(镜像 / 卷 / 缓存)---${NC}"
  docker system df 2>/dev/null || true
  echo ""
  echo "${YELLOW}--- docker compose ps 快照 ---${NC}"
  docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted ps 2>/dev/null || true
  echo ""
  echo "${YELLOW}--- 关键进程(docker / buildkit / containerd)---${NC}"
  ps aux | grep -E "docker|buildkit|containerd" | grep -v grep | head -10 || true

  # ── 失败回滚 git HEAD · 防三向脱钩 ──
  # OLD_HEAD_SAVED 仅在 1/7 已真实 git reset 后被赋值 · 失败发生在 reset 之前则不回滚
  if [ -n "${OLD_HEAD_SAVED:-}" ]; then
    local cur_head
    cur_head=$(git rev-parse HEAD 2>/dev/null || echo "?")
    if [ "$cur_head" != "$OLD_HEAD_SAVED" ]; then
      echo ""
      echo "${YELLOW}--- 回滚 git HEAD:${cur_head:0:8} → ${OLD_HEAD_SAVED:0:8}(防三向脱钩)---${NC}"
      git reset --hard "$OLD_HEAD_SAVED" 2>&1 | tail -2 || \
        echo "${RED}  ⚠ git reset 也失败 · 服务器需手动:git reset --hard ${OLD_HEAD_SAVED:0:8}${NC}"
    else
      echo ""
      echo "${YELLOW}--- HEAD 未移动(失败发生在 reset 前)· 不回滚 ---${NC}"
    fi
  fi

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
banner "1/7 · git pull · 拉最新代码"
# ============================================================
OLD_HEAD=$(git rev-parse HEAD)
echo "  当前 HEAD = $(git rev-parse --short HEAD)"
[ "$FORCE_REBUILD" = "true" ] && warn "FORCE_REBUILD=true · 跳过 fast-path · 强制走完整流程"
git fetch origin main 2>&1 | tail -3
NEW_HEAD=$(git rev-parse origin/main)

if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
  if [ "$FORCE_REBUILD" = "true" ]; then
    warn "HEAD 已是最新 · 但 FORCE_REBUILD=true · 不退出 · 继续强制重建"
    NEW_HEAD_SHORT=$(git rev-parse --short HEAD)
    # HEAD 没动 · OLD_HEAD_SAVED 保持空 · 失败时 trap 不会回滚(无可回滚)
  else
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
else
  git reset --hard origin/main 2>&1 | tail -1
  NEW_HEAD_SHORT=$(git rev-parse --short HEAD)
  # ⚠ 关键:reset 真正发生后才设 OLD_HEAD_SAVED · trap 据此判定是否回滚
  OLD_HEAD_SAVED=$OLD_HEAD
  ok "更新到 HEAD = ${NEW_HEAD_SHORT}(失败时可回滚到 ${OLD_HEAD:0:8})"

  echo ""
  echo "${CYAN}─── 本次更新的 commit ───${NC}"
  git log --oneline "${OLD_HEAD}..${NEW_HEAD}" | head -20
fi

# ============================================================
banner "2/7 · 计算变更范围 · 决定需要做什么"
# ============================================================
if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
  # FORCE_REBUILD 路径:HEAD 没变 · 跳 diff 直接走强制
  echo "  (HEAD 未变 · 跳 diff 判定 · 由 FORCE_REBUILD 接管)"
  CHANGED=""
  TOTAL_FILES=0
else
  CHANGED=$(git diff --name-only "${OLD_HEAD}" "${NEW_HEAD}")
  TOTAL_FILES=$(echo "$CHANGED" | grep -c "" || true)
  echo "  本次变更 ${TOTAL_FILES} 个文件"
fi
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

# ── ADR 0029 DP4:FORCE_REBUILD 顶替 diff 判定 ──
# 在所有 diff-based flag 计算完成之后强行 OR 上 · 不破坏正常 push 部署的 diff 判定路径
if [ "$FORCE_REBUILD" = "true" ]; then
  warn "FORCE_REBUILD=true · 忽略 diff · 强制重建 api + worker + web"
  NEED_BUILD_API=true
  NEED_BUILD_WEB=true
  NEED_COMPOSE_UP=true
fi

if [ "$NEED_BUILD_API" = "false" ] && [ "$NEED_BUILD_WEB" = "false" ] \
   && [ "$NEED_COMPOSE_UP" = "false" ] && [ "$NEED_CADDY_RELOAD" = "false" ] \
   && [ "$NEED_ALEMBIC" = "false" ]; then
  ok "本次变更只涉及 docs/scripts/ADR · 无需重建任何容器"
fi

# ============================================================
banner "3/7 · 执行 docker 层动作"
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
  # ── ADR 0029 DP2 静默护栏三件套 ──
  # · timeout 1500 · 硬上限 25min · 防 docker build 卡死无限挂(2026-05 #57 故障根因 = 无超时)
  #   ⚠️ 2026-05-28 实测调整:旧值 900s 太紧 · force_rebuild 同时 build api+worker+web 真实需要 ~14min30s
  #     (api pip cache hit 8min · worker 2min · web build 4min 没 cache mount · 见 task #282 backlog)
  #     新值 1500s (25min) 留 ~10min 余量 · 仍在外层 GitHub timeout-minutes 30 之内(DP7 兜底)
  # · BUILDKIT_PROGRESS=plain env · 流式 build log(替代原 `2>&1 | tail -40` 后置吞输出)
  #   ⚠️ 注:`docker compose up` 不支持 --progress flag(只 `docker compose build` 支持)
  #        → 走 BuildKit 客户端层 env var · 对 compose up --build 内部 build 也生效 · Docker 19.03+ 支持
  # · 失败诊断 · trap on_err 自动打出磁盘/缓存/进程快照
  # ✅ 正常路径不变 · 仅在【失败 / 卡死】时显著提速排障
  # 暴露 BuildKit · DOCKER_BUILDKIT=1 是 cache mount + syntax 1.7 必需
  export DOCKER_BUILDKIT=1
  export BUILDKIT_PROGRESS=plain
  timeout 1500 $COMPOSE up -d --build --force-recreate --no-deps "${RECREATE_SVCS[@]}"
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
banner "4/7 · alembic migration(如有新文件)"
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
banner "5/7 · Caddy 配置 reload(如有改动)"
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
banner "6/7 · 健康检查"
# ============================================================
STAGE="6/7 healthcheck"

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

# ============================================================
banner "7/7 · 缓存清理(温和版 · 7 天未用)"
# ============================================================
# ADR 0029 DP3:部署成功后清理 7 天未用的 BuildKit 缓存碎片 · 防 30GB 失控(2026-05 #57 故障根因)
# 温和策略:--filter until=168h · 保 7 天内热缓存 · 不影响下一次部署的 cache mount 命中
# 兜底层:prune 失败不阻塞 deploy 成功路径(健康检查已过 · 此步纯卫生)
STAGE="7/7 cache prune"
echo "  清 7 天未用的 BuildKit 缓存..."
docker builder prune -f --filter "until=168h" 2>&1 | tail -5 || warn "prune 失败 · 不阻塞 deploy(健康检查已过)"
echo ""
echo "${CYAN}─── 当前缓存占用(prune 后)───${NC}"
docker system df 2>&1 | head -10 || true

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
