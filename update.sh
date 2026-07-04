#!/bin/bash
# 点金 Midas · 一键更新脚本
# 2026-05-21 · 模式 B 全栈
#
# 用法(服务器):
#   cd /opt/midas
#   bash update.sh                       # ★默认 pull 模式(拉 ACR 镜像 · 零本地 build)
#   DEPLOY_MODE=build bash update.sh     # 兜底:VPS 本地 build(ACR/Actions 故障时退老链)
#
# ── ★部署模式(DEPLOY_MODE · 详见下方定义处 + docs/decisions/0044)──────────────────
#   pull(默认常态) = CI 在 GitHub Actions build 三镜像推 ACR → 这里只 docker compose pull
#                     + recreate(零构建负载 · 同机重型 build 整机卡死根源物理消失)。
#   build(兜底)    = 老链:VPS 本地 docker compose build 三镜像(顺序防 OOM)→ recreate。
#
# 行为:
#   1. git pull(用 credential.helper store · 不弹 PAT)
#   2. 对比 HEAD 前后差异 · 决定要不要 rebuild + 哪些服务
#   3. 智能动作(pull:拉改动服务的镜像 / build:本地 build 改动服务):
#        · apps/api / apps/worker 改了 → 重建 api + worker
#        · apps/web / packages 改了 → 重建 web
#        · docker/*.yaml 改了 → docker compose up -d --build(全栈影响)
#        · deploy/Caddyfile 改了 → cp + systemctl reload caddy
#        · apps/api/alembic/versions/ 新增 → docker exec midas-api alembic upgrade head
#        · 只是 docs / scripts 改了 → 不做任何动作
#   4. 健康检查 · 5 服务 healthy + worker running
#   5. 打印最终状态 · pull 模式额外催收旧 sha 镜像(保留最近 3 个供回滚)
#
# 设计:幂等 · 安全 · 一句话搞定所有迭代部署。

set -euo pipefail

RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; MAGENTA=$'\033[1;35m'; NC=$'\033[0m'

STAGE="init"
# ── ADR 0029 DP4:外部 FORCE_REBUILD 开关(GitHub Actions inputs / 服务器手动) ──
# true → 跳 "已是最新" + 跳 diff 判定 · 强制处理 api+worker+web 三服务(用于 cache 卡脏 / 强制刷依赖)。
#   ★语义随 DEPLOY_MODE 而定:build 模式=本地强制重 build 三镜像;pull 模式=强制 re-pull 三镜像 sha
#   + recreate(要真刷镜像内容,走 workflow_dispatch 会连带无条件重跑 build-push job 重推 ACR)。
# 缺省 false · 不影响正常 push 部署
FORCE_REBUILD="${FORCE_REBUILD:-false}"
# ── ★部署基建根治 · DEPLOY_MODE 双模式(build 挪出 VPS · 阶段4 起 pull 为默认常态)──────
# pull(★默认 · 新部署链常态)= CI(deploy.yml 的 build-push job)在 GitHub Actions build 好
#         三镜像推阿里云 ACR → VPS 只 docker compose pull + recreate(零构建负载 · i18n 批0
#         「同机重型 build 无内存余量」整机卡死根源物理消失 · build 失败=Actions 红=部署不跑=生产不动)。
# build(兜底 · 退老链)= 现状旧链:VPS 上 docker compose build 三镜像(顺序防 OOM)→ recreate。
#         ★何时用:ACR/Actions 故障、或需在 VPS 本地快速验证某分支镜像时。触发方式:
#         GitHub Actions 手动 workflow_dispatch → deploy_mode=build;或服务器 DEPLOY_MODE=build bash update.sh。
# pull 模式前置(已配 · VPS /opt/midas/.env):MIDAS_REGISTRY=<VPC registry>/midastrade
#   (compose image: 插值用 · 缺失会被 3/7 的 fail-fast 守卫明确拦截)· VPS 已 docker login ACR(store 持久)。
DEPLOY_MODE="${DEPLOY_MODE:-pull}"
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
# ── ADR 0031 · DP1 · fast-path 误判修复(deploy.yml env 注入优先 · 否则 disk 自算)──
# env 注入场景(deploy.yml SSH 命令在 git reset --hard 之【前】算 OLD_HEAD)
#   · OLD_HEAD = reset 前的 server HEAD(= 上次部署的 commit)
#   · NEW_HEAD = reset 后 HEAD(= origin/main · 本次目标 commit)
#   · 真实反映"server 跑哪个 commit vs origin 想推到哪个 commit"
#   · 避免 0029 hotfix-2(`git reset --hard origin/main`)让 disk HEAD 在
#     update.sh 启动前已等于 origin/main · diff 判定恒空 fast-path 误判的副作用
# disk 自算场景(产品方手动 SSH 跑 `bash update.sh` · env 未注入)
#   · 退化到原行为 · 与 ADR 0031 之前一致
#   · ⚠️ 若手动 SSH 前已自行 `git reset --hard origin/main`,会触发 fast-path 误判
#     (跟修前同款副作用 · banner 会 warn 提示)
OLD_HEAD_SRC="env"
NEW_HEAD_SRC="env"
if [ -z "${OLD_HEAD:-}" ]; then
  OLD_HEAD=$(git rev-parse HEAD)
  OLD_HEAD_SRC="disk"
fi
echo "  当前 HEAD = $(git rev-parse --short HEAD)"
[ "$FORCE_REBUILD" = "true" ] && warn "FORCE_REBUILD=true · 跳过 fast-path · 强制走完整流程"

# git fetch:env 模式时 deploy.yml 已 fetch(冗余 no-op);disk 模式时必跑
git fetch origin main 2>&1 | tail -3
if [ -z "${NEW_HEAD:-}" ]; then
  NEW_HEAD=$(git rev-parse origin/main)
  NEW_HEAD_SRC="disk"
fi

# Banner 提示来源 · 手动 SSH 场景一眼看出"env 未注入 · 可能误判"
if [ "$OLD_HEAD_SRC" = "env" ] && [ "$NEW_HEAD_SRC" = "env" ]; then
  echo "  OLD_HEAD = ${OLD_HEAD:0:8} · NEW_HEAD = ${NEW_HEAD:0:8}(env 注入 · deploy.yml 在 reset 前后算)"
else
  echo "  OLD_HEAD = ${OLD_HEAD:0:8} · NEW_HEAD = ${NEW_HEAD:0:8}(disk 自算)"
  warn "OLD_HEAD/NEW_HEAD env 未注入 · 退化到 disk 自算(手动 SSH 跑场景 · 若已 reset 则 fast-path 可能误判)"
fi

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
  # ★ core.quotePath=false:git 默认对非 ASCII(中文)路径加引号 + 八进制转义(如
  #   "apps/web/public/academy-img/A10-\351\205..png"),致该行行首是 " → 下方各
  #   `grep -qE "^apps/web/"` 等锚点不匹配 → 纯中文名文件改动(如 academy 中文配图单图替换)
  #   被漏判、NEED_BUILD_WEB=false、容器不重建(A10 重画版单图事故根因 · task_e2c38de3)。
  #   设 false 让路径原样 UTF-8 输出,^ 锚点恢复正常匹配;per-command 不污染全局/仓库 config。
  CHANGED=$(git -c core.quotePath=false diff --name-only "${OLD_HEAD}" "${NEW_HEAD}")
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
NEED_BUILD_VIBE=false      # P1-4b:midas-vibe 镜像源(deploy/vibe/Dockerfile)改 → 重建镜像
NEED_RESTART_VIBE=false    # P1-4b:vibe 运行时挂载文件(job/celery_app/loader)改 → 只重起 vibe-worker

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

# P1-4b 方案戊:midas-vibe 是 image:(非 compose build)· Dockerfile 改 → 必须手动 docker build
if echo "$CHANGED" | grep -qE "^deploy/vibe/Dockerfile$"; then
  NEED_BUILD_VIBE=true
  echo "  ${MAGENTA}▸${NC} 检测到 deploy/vibe/Dockerfile 改动 → 重建 midas-vibe 镜像 + 重起 vibe-worker"
fi
# vibe 运行时挂载代码(run_backtest_job/vibe_celery_app)或 loader 改 → 只重起 vibe-worker(不重建镜像)
if echo "$CHANGED" | grep -qE "^deploy/vibe/.*\.py$|^apps/api/app/services/backtest/midas_ch_loader\.py$"; then
  NEED_RESTART_VIBE=true
  echo "  ${MAGENTA}▸${NC} 检测到 vibe 挂载代码/loader 改动 → 重起 vibe-worker(挂载即生效 · 不重建镜像)"
fi

# alembic migration 新增(只看新文件 · 不看修改)
NEW_MIGRATIONS=$(git -c core.quotePath=false diff --name-only --diff-filter=A "${OLD_HEAD}" "${NEW_HEAD}" | grep "^apps/api/alembic/versions/.*\.py$" || true)
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
  warn "FORCE_REBUILD=true · 忽略 diff · 强制重建 api + worker + web + alembic upgrade head"
  NEED_BUILD_API=true
  NEED_BUILD_WEB=true
  NEED_COMPOSE_UP=true
  # ★ 2026-06-19 翻车修:force_rebuild 也强制跑迁移(幂等 · 已 head 则 no-op)。
  #   坑:迁移文件早被前面的 git reset --hard 带进 VPS 树 → OLD..NEW diff 无新文件 → NEED_ALEMBIC=false
  #   → 容器是新码但表没建 → authed 查表 500。force_rebuild = "prod 全面对齐 main",必须含表结构。
  NEED_ALEMBIC=true
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

# ── P1-4b 方案戊:midas-vibe 是 image:(非 compose build)→ 任何 compose up 前先确保镜像存在 ──
# 首次(镜像不存在)或 deploy/vibe/Dockerfile 改 → docker build(compose 不会自动 build image: 服务)。
# ⚠ 必须在下方 compose up 之前:否则 plain `compose up -d` 引用 midas-vibe:0.1.9 会因镜像缺失失败。
if [ "$NEED_BUILD_VIBE" = "true" ] || ! docker image inspect midas-vibe:0.1.9 >/dev/null 2>&1; then
  section "构建 midas-vibe:0.1.9 镜像(image: · compose 不自动 build)"
  export DOCKER_BUILDKIT=1
  timeout 600 docker build -t midas-vibe:0.1.9 deploy/vibe
  NEED_RESTART_VIBE=true   # 新镜像 → 标记重起 vibe-worker 应用
  ok "midas-vibe:0.1.9 镜像就绪"
fi

if [ ${#RECREATE_SVCS[@]} -gt 0 ]; then
  section "重建有代码改动的无状态服务:${RECREATE_SVCS[*]}(DEPLOY_MODE=$DEPLOY_MODE)"

  if [ "$DEPLOY_MODE" = "pull" ]; then
    # ════════════════════════════════════════════════════════════════════
    # ── ★pull 模式(build 挪出 VPS · 阶段4 起为默认常态)────────────────────────────
    # CI(deploy.yml 的 build-push job)已在 GitHub Actions build 好三镜像推 ACR;VPS 只 docker compose
    # pull 精确 sha tag → recreate · 零构建负载 · i18n 批0 整机卡死根源(同机重型 build)物理消失。
    #   · MIDAS_IMAGE_TAG=NEW_HEAD(全 40 位 sha · 与 CI push 的 tag 一致 · compose image: 插值用)
    #   · MIDAS_REGISTRY 由 VPS /opt/midas/.env 提供(VPC registry+命名空间 · compose 自动读 .env)
    #   · VPS 已 docker login ACR(credential store 持久 · 故此处不显式 login)
    # ════════════════════════════════════════════════════════════════════
    export MIDAS_IMAGE_TAG="$NEW_HEAD"

    # ── ★fail-fast 守卫:MIDAS_REGISTRY 未配 → 明确报错 + 指引(2026-07-04 阶段3 首跑翻车)──
    #   VPS /opt/midas/.env 漏配 MIDAS_REGISTRY 时,compose image: 的 ${MIDAS_REGISTRY:+…} 退化成
    #   裸名 `midas-web:<sha>` → docker 去 docker.io 找 → `pull access denied`(cryptic·难排查)。
    #   ★注:MIDAS_REGISTRY 由 .env 提供、compose 自己读;bash 进程里该 shell 变量本就是空的,
    #   所以【绝不能】查 `$MIDAS_REGISTRY` shell 变量(必误报)。正确做法=用 `compose config`
    #   全量解析取 web 服务的 image 行(compose 真正会拉的镜像名)做地面真相:带 registry 前缀=
    #   含 '/',裸名=不含。★用全量 config(自 compose v1 通用)而非 `--images`(旧版无此 flag →
    #   空输出会误报拦截配置正确的 .env)。grep 定位到 `image: …midas-web…` 行(context 行是别的 key)。
    _web_img=$($COMPOSE config 2>/dev/null | grep -E '^\s*image:.*midas-web' | head -1 || true)
    if ! printf '%s' "$_web_img" | grep -q '/'; then
      echo "${RED}  ✗ pull 模式:compose 解析出的 web 镜像 =「${_web_img:-<空>}」· 无 registry 前缀${NC}"
      echo "${RED}    根因:MIDAS_REGISTRY 未生效(VPS /opt/midas/.env 缺此变量 → image 退化裸名 → 拉取被拒)${NC}"
      echo "${RED}    修复:在 VPS /opt/midas/.env 加一行(VPC 地址 + 命名空间 · 无尾斜杠):${NC}"
      echo "${RED}    MIDAS_REGISTRY=crpi-kejjqltz4vumnjmv-vpc.cn-hongkong.personal.cr.aliyuncs.com/midastrade${NC}"
      echo "${RED}    或退回 build 兜底:DEPLOY_MODE=build bash update.sh${NC}"
      false   # 触发 ERR trap → on_err 诊断快照 + 回滚 git HEAD(此刻尚未 pull/recreate · 站点不受影响)
    fi
    ok "compose 解析 web 镜像带 registry 前缀:${_web_img}"

    section "pull 改动服务:${RECREATE_SVCS[*]}(tag=$MIDAS_IMAGE_TAG · 零本地 build)"
    timeout 600 $COMPOSE pull "${RECREATE_SVCS[@]}"
    ok "镜像 pull 完成(tag=$MIDAS_IMAGE_TAG · VPS 零构建负载)"
  else
    # ── build 模式(兜底 · 阶段4 起非默认 · 退老链)· 以下与改造前一字不变 ────────────────
    # ── 2026-06-19 翻车修:构建【前】清陈旧 buildkit 缓存(失败时下方 post 清理到不了)──
    #   force-rebuild 三镜像 + pip 重试曾把 build cache 堆到 17.91GB · 压盘加剧超时/OOM。
    #   --keep-storage 10GB 保留近期层缓存(含 pip 依赖层)· 只清陈旧 · 不动在用镜像。
    echo "  ${MAGENTA}▸${NC} 构建前清陈旧 buildkit 缓存(--keep-storage 10GB · 保留依赖层)"
    docker builder prune -f --keep-storage 10GB 2>&1 | tail -3 || warn "pre-build prune 失败 · 不阻塞"

    # 暴露 BuildKit · DOCKER_BUILDKIT=1 是 cache mount + syntax 1.7 必需
    # BUILDKIT_PROGRESS=plain · 流式 build log(失败时易排障)
    export DOCKER_BUILDKIT=1
    export BUILDKIT_PROGRESS=plain

    # ── 2026-06-30 事故修(#91 部署 OOM · 整站宕机)· 顺序 build · 绝不并行 ──
    #   docker compose 对多 service 默认【并行 build】三镜像同抢 7G 内存 → OOM → 宕机(#91 根因)。
    #   一个一个 build(任意时刻只 1 个占内存峰值)· 全 build 成功后再一次性 --no-build 重建。
    #   用 `docker compose build`(非裸 docker build):自动带 web 的 NEXT_PUBLIC_API_URL(0016)。
    #   ★注:pull 模式上线后这条重型 build 路径退居 force_rebuild 兜底(内存墙根源随之退场)。
    for svc in "${RECREATE_SVCS[@]}"; do
      section "顺序 build:${svc}(独占内存峰值 · 防并行 OOM)"
      timeout 1800 $COMPOSE build "$svc"
      ok "${svc} 镜像 build 完成"
    done
  fi

  # ── 两模式共用:pull/build 完后一次性重建容器 ──
  section "镜像就绪 · 一次性重建容器(--no-build --force-recreate --no-deps)"
  # --no-build      pull/build 已就绪 · 这步绝不 build(pull 模式更是物理无 build 能力 · 双保险)
  # --force-recreate 用新镜像重建容器(pull 模式 sha tag 每次不同 · 天然强制重建 · 不靠同名兜底)
  # --no-deps       只动无状态服务 · 绝不触碰 postgres/clickhouse/redis(数据卷不动 · 红线)
  $COMPOSE up -d --no-build --force-recreate --no-deps "${RECREATE_SVCS[@]}"
  ok "force-recreate 完成:${RECREATE_SVCS[*]}(有状态容器未触碰 · DEPLOY_MODE=$DEPLOY_MODE)"
elif [ "$NEED_COMPOSE_UP" = "true" ]; then
  # 仅 compose yaml 改动(无后端/前端代码改动)→ 普通 up -d 应用配置差异。
  # 不 --build、不 --force-recreate:compose 只重建"配置确实变了"的服务,有状态容器不会被无故重建。
  section "compose 配置变更 · docker compose up -d 应用(不 --build / 不 --force-recreate)"
  $COMPOSE up -d 2>&1 | tail -40
  ok "compose up 返回"
else
  skip "docker 容器无需变更"
fi

# ── P1-4b 方案戊:vibe-worker 重起(应用运行时挂载代码/loader 改动,或新镜像)──────
# midas-vibe 是 image: · 不随上面 RECREATE_SVCS 的 --build 走 · 单独 force-recreate 应用。
# --no-deps 只动 vibe-worker(不碰 redis/clickhouse 等有状态依赖)。
if [ "$NEED_RESTART_VIBE" = "true" ]; then
  section "重起 vibe-worker(应用挂载代码/新镜像 · --no-deps 不碰其它服务)"
  $COMPOSE up -d --force-recreate --no-deps vibe-worker 2>&1 | tail -20
  ok "vibe-worker 重起"
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
banner "7/7 · 缓存清理(按大小催收 · 压到 10GB)"
# ============================================================
# ADR 0029 DP3 → 0032 修正(2026-05-29 磁盘满 43GB 复盘):
#   旧版 `--filter until=168h` 只清【7 天未用】的缓存;但 cache mount(pnpm store /
#   .next/cache / pip · ADR 0031)天天 build 复用、永远 <7 天 → 这条护栏对热缓存全程空转,
#   密集部署下堆到 43GB 把磁盘打满。根因是"按年龄"门槛,不是配置丢失。
# 改为【按大小】催收:--keep-storage 10GB · 与部署频率解耦 · 每次部署都把 BuildKit 缓存
#   按 LRU 压到 10GB,保留最近的热 cache mount(几百 MB)→ 不伤下次 build 速度,只砍堆积旧层。
# 兜底层:① daemon.json builder.gc 加【无 filter 的 15GB 硬上限】催收规则(N2 修正 · 服务器侧);
#         ② prune 失败不阻塞 deploy 成功路径(健康检查已过 · 此步纯卫生)。
STAGE="7/7 cache prune"
# ★build 缓存清理【按模式分叉】(2026-07-04 磁盘墙事故根治):
#   pull 模式 → VPS 永不 build → BuildKit 缓存 100% 是死重(21G 历史遗留曾撑满 /dev/vda3 →
#     ClickHouse 可用空间归 0 → 写不进 → api 500 → 前端"后端不可达")→ `prune -af` 清光
#     (★-a 连 "in-use" 死缓存一起清 · --keep-storage 保不住的那 ~11G 非 -a 不动 · 正是死重来源)。
#   build 兜底模式 → 下次 VPS 还要本地 build → 保留 `--keep-storage 10GB` 热缓存(不伤 build 速度)。
if [ "$DEPLOY_MODE" = "pull" ]; then
  echo "  pull 模式:清光 BuildKit 缓存(VPS 不 build · 缓存全死 · prune -af)..."
  docker builder prune -af 2>&1 | tail -5 || warn "prune 失败 · 不阻塞 deploy(健康检查已过)"
else
  echo "  build 模式:按大小催收 BuildKit 缓存(保留最近 10GB 热缓存)..."
  docker builder prune -f --keep-storage 10GB 2>&1 | tail -5 || warn "prune 失败 · 不阻塞 deploy(健康检查已过)"
fi

# ── ★pull 模式:催收旧 sha 镜像(保留最近 KEEP 个供回滚)· 阶段4(VPS 磁盘压力新来源)──────
#   pull 模式每次部署 pull 新 sha 的 midas-{svc} 镜像 → VPS 累积旧 tag(build 模式无此累积)。
#   策略:每个 ACR repo 只留最近 KEEP 个 sha tag(newest-first · docker images 默认序),更老删。
#   ★关键:MIDAS_REGISTRY 由 .env 提供、compose 自己读,bash 进程里该 shell 变量【本就是空的】,
#     所以【绝不能】用 $MIDAS_REGISTRY 拼 repo(会得到 `/midas-web` · 且 [ -n ] 恒假 → 整段死代码)。
#     正确做法=和 3/7 守卫同源:从 `compose config` 取 web 完整镜像名(含 registry)反推 ACR repo 前缀。
#   ★安全四重保:① 只碰 <registry>/midas-{api,worker,web} 这三个 repo · 绝不碰 pg/ch/redis/vibe/xshot
#     ② docker rmi 【不加 -f】→ 在用镜像 docker 自己拒删(if 吞 · 不阻塞)③ latest 永不删(回滚指针)
#     ④ 显式跳过所有容器(含停止)正引用的 ref。
#   ★set -e 兼容:grep -q/rmi 全走 if(条件豁免 set -e)· 管道尾 `|| true` 防 grep 返 1 误触 ERR。
if [ "$DEPLOY_MODE" = "pull" ]; then
  KEEP_IMAGES=2   # 每 repo 留最近 2 个 sha(当前 + 1 回滚目标)+ latest + 在用 · 2026-07-04 收紧(原 3)
  # compose config 解析出的 web 完整镜像名(含 registry)→ 反推 repo 前缀 <registry>/midastrade
  _web_full=$($COMPOSE config 2>/dev/null | grep -E '^[[:space:]]*image:.*midas-web' | head -1 | sed -E "s/.*image:[[:space:]]*//; s/[\"']//g; s/[[:space:]]//g" || true)
  _reg_ns=$(printf '%s' "$_web_full" | sed -E 's#/midas-web(:.*)?$##')
  # _reg_ns 含 '/' = 有 registry/namespace 前缀(可清);否则(裸名 / 空)跳过 · 不误删本地镜像
  if printf '%s' "$_reg_ns" | grep -q '/'; then
    echo ""
    echo "  ${MAGENTA}▸${NC} pull 模式催收旧 sha 镜像(每 repo 留最近 ${KEEP_IMAGES} 个 + latest + 在用 · repo 前缀=${_reg_ns})"
    in_use_refs=$(docker ps -a --format '{{.Image}}' 2>/dev/null | sort -u || true)
    for svc in api worker web; do
      repo="${_reg_ns}/midas-${svc}"
      old_tags=$(docker images "$repo" --format '{{.Tag}}' 2>/dev/null | grep -vx 'latest' | tail -n +$((KEEP_IMAGES + 1)) || true)
      [ -n "$old_tags" ] || continue
      while IFS= read -r tag; do
        [ -z "$tag" ] && continue
        ref="${repo}:${tag}"
        if printf '%s\n' "$in_use_refs" | grep -qxF "$ref"; then
          continue   # ★在用镜像(含停止容器引用)· 绝不删
        fi
        if docker rmi "$ref" >/dev/null 2>&1; then
          echo "    ✓ 删旧镜像 ${svc}:${tag:0:12}…"
        fi
      done <<< "$old_tags"
    done
    docker image prune -f >/dev/null 2>&1 || true   # 清 untag 后悬空层(安全 · 只清无 tag 无引用)
  else
    warn "pull 模式镜像催收跳过:compose config 未解出带 registry 前缀的 web 镜像(_reg_ns=${_reg_ns:-<空>})"
  fi

  # ── ★补清无引用的旧【裸名】镜像(build 时代遗留 · 已被 ACR 镜像取代)· 2026-07-04 ──────
  #   裸名 midas-{api,worker,web}(无 registry 前缀)是 build 时代 VPS 本地 build 产物。web 已切 ACR
  #   镜像 → 裸名 midas-web 成死镜像;api/worker 若仍跑裸名(在用)则必须保住。只碰 midas-{api,worker,web}
  #   三个裸名 repo(不碰 vibe/xshot/pg/ch/redis)。
  #   ★★真正的安全保障 = `docker rmi` 【不加 -f】:在用镜像的最后一个 tag,daemon 直接拒删(exit 1·
  #     if 吞掉·不阻塞)—— 对抗审查实证:这一层【绝不误删在跑/停容器的镜像】。
  #   ★grep 守卫只是【best-effort 降噪】(少试几次注定失败的 rmi):`{{.Image}}` 不规范化(compose 隐式
  #     :latest 的容器可能显示裸名 `midas-api` 而非 `midas-api:latest`,或显示 image ID)→ 故【也】比对裸名
  #     repo 形式兜住 compose 隐式 tag 的常见情形;ID 情形则由上面 rmi-不加-f 兜底。
  in_use_bare=$(docker ps -a --format '{{.Image}}' 2>/dev/null | sort -u || true)
  for svc in api worker web; do
    for btag in $(docker images "midas-${svc}" --format '{{.Tag}}' 2>/dev/null || true); do
      bref="midas-${svc}:${btag}"
      # best-effort 跳过:精确 ref 在用 · 或裸名 repo 形式在用(compose 隐式 :latest 常显示裸名)
      if printf '%s\n' "$in_use_bare" | grep -qxF "$bref" \
        || printf '%s\n' "$in_use_bare" | grep -qxF "midas-${svc}"; then
        continue
      fi
      # 兜底安全:即便上面漏判,rmi 不加 -f 对在用镜像最后一个 tag 会被 daemon 拒删(if 吞 · 不阻塞)
      if docker rmi "$bref" >/dev/null 2>&1; then
        echo "    ✓ 删死裸名镜像 ${bref}(已被 ACR 取代)"
      fi
    done
  done
fi

echo ""
echo "${CYAN}─── 当前缓存/镜像占用(prune 后)───${NC}"
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
