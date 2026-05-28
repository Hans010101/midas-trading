# 0029 · 部署健壮性专项(N1 部署故障教训) · 设计方案

## 状态

**Draft · 待产品方审**(2026-05-28)· 仅方案,不含实现代码、不改任何运行代码。

承接:N1(ADR-0028 告警降噪)部署故障 —— 一次 30min timeout 失败 + 三次假绿 + 一次手动救场,
攒齐了一串教训,趁热固化成机制。

> 🔴 红线:本文只是部署运维流程加固;不改业务代码、不改告警/虚拟交易任何核心逻辑。
> 实施期每条改动**显式标注生效路径**(deploy.yml 独立改 / update.sh 需先部署一次才生效 / Dockerfile 下次 build 生效)。

---

## 0. 故障复盘 · N1 部署 5 个坑(按踩到顺序)

| # | 现象 | 直接根因 | 影响 |
|---|---|---|---|
| 1 | `#57` push 部署 build 阶段 stdout 静默 29.5 分钟 · 30min hard timeout 被砍 | builder cache 堆 30GB + `pip install --no-cache-dir` 每次从 PyPI 重拉(香港→PyPI 慢)→ build 装依赖 ~40 分钟 | 部署失败 · 服务器 SSH 命令被砍但 git 已 checkout 到 7b40173 |
| 2 | build 静默期间 GitHub Actions UI / `gh run view` 看不到 stdout · 只能等 30min timeout 自动结束 | `update.sh` 用 `tail -40` 缓冲输出 · build 期间 stdout 不流式 · 失败时无诊断信息 | 排错被动 · 12 分钟还是 30 分钟没差别 |
| 3 | `#57` 失败后产品方手动 `docker builder prune -f` 回收 24.44GB 时,触发运行容器 "rw layer snapshot not found" 报错 + 触发 docker 自动用旧 image 重建 api/worker 容器 | 缓存清理时机不安全(对运行中容器太狠) | 旧容器被替换为另一个旧容器(没用 N1 新 image)· 假复活假象 |
| 4 | `#58/#59` 两次 dispatch 24-25s "假绿":`update.sh` 检测 OLD==NEW 走"已是最新版本"快速路径 / `git diff` 检测无文件改动走"docs/scripts 无需重建"快速路径 | `update.sh` 用 git HEAD 判版本 · 当 git HEAD 已推进但 image/DB 没跟上(脱钩态)时误判 | 三次假绿 · 用户误以为 N1 已上线 · 实际生产仍跑旧码 |
| 5 | `#57` 中途被砍时 `git checkout -f main` 已执行 · git HEAD 推进到 7b40173 · 但 docker image / DB schema 仍是旧的 → "git HEAD ≠ image ≠ DB" 三向脱钩 · 后续部署连环误判 | `update.sh` 第 1 步 `git reset` 在所有真实动作之前 · 失败时不回滚 | 后续 3 次部署全部假绿 · 最终靠产品方 SSH `git reset --hard b3e90bd` + 手动跑 docker compose + alembic 才回血 |

> N1 实际上线时间线:`push #57(30min timeout)` → `dispatch #58(假绿)` → `redeploy 空 commit + dispatch #59(假绿)` → 产品方 SSH `git reset --hard b3e90bd` → `dispatch #60(完整路径 · 又卡 12min build)` → 产品方 SSH 直接 `bash update.sh` 跑完(成功)。**整个事件 ~3 小时 · 本来 8 分钟能搞定**。

---

## 1. 坑 1 · pip `--no-cache-dir` + 香港→PyPI 慢 = 每次 build ~40min

### 现状
- `apps/api/Dockerfile:15` · `RUN pip install --no-cache-dir -e ".[dev]"`(1 次)
- `apps/worker/Dockerfile:15+18` · 同 `--no-cache-dir`(2 次:api 依赖 + worker 依赖)
- `apps/web/Dockerfile` · 已用 "manifest-first" 模式让 `pnpm install` 命中 Docker 层缓存(slim 改动不重装),不存在此问题
- BuildKit cache mount 全部三个 Dockerfile 都**没用**
- builder cache 堆 30GB 是另一种隐性堆积(每次 build 的中间层,跟 pip wheel 缓存解耦,但同一仓库)

### 修复选项

#### A · BuildKit cache mount(推荐 · 现代方案)
```dockerfile
# apps/api/Dockerfile
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -e ".[dev]"          # 去掉 --no-cache-dir
```
- pip wheel cache 持久化到 buildkit 管理的 volume · 跨 build 复用
- BuildKit 自身有大小阈值 GC · 不会无限堆 30GB
- web 也可同样加 pnpm store cache mount:`--mount=type=cache,target=/root/.local/share/pnpm/store`
- 需 docker compose 启用 BuildKit(`DOCKER_BUILDKIT=1` env 或 `docker compose` 自带 BuildKit)

#### B · 持久 docker volume(更复杂)
- 挂一个命名 volume 到 `/root/.cache/pip` · 类似 cache mount 但需 compose 显式声明
- 比 A 灵活但配置更碎

#### C · PyPI 国内镜像(简单 · 治标)
```dockerfile
RUN pip install --no-cache-dir -e ".[dev]" \
    -i https://pypi.tuna.tsinghua.edu.cn/simple
```
- 解决"香港→PyPI 慢" · 首次也快
- 不解决"每次重装"问题 · 只让"重装快"
- 风险:清华镜像偶尔同步延迟新版包(教学用足够,大不了 fallback)

#### D · A + C 组合(推荐)
- A 解决"重装"问题(cache 跨 build 复用)
- C 解决"首次/cache miss 时的慢"问题(国内镜像)
- 两个独立机制叠加

### 评估:能否顺带缓解 builder cache 堆积?
- **部分缓解,不能根治**。`pip wheel cache` 与 `docker builder cache`(Dockerfile 层缓存)是两套机制
  - pip cache mount(A)让 pip 不重下载 wheel · 但每次 `RUN pip install` 仍可能产生新的 Docker layer
  - Docker builder cache 堆积主要来自频繁 build · A 让 wheel 命中后**单次 build 中间层更稳定**,但 N 次 build 仍会产生 N 个 layer
- 所以坑 1 解决"build 慢",坑 3 单独处理"cache 堆积"

### 改动范围 + 生效路径
- 文件:`apps/api/Dockerfile` / `apps/worker/Dockerfile` / 可选 `apps/web/Dockerfile`
- 生效路径:**下次部署 build 时生效**(Dockerfile 在 git 仓库里,部署 git pull 后下次 build 用新版)
- **不影响**:运行容器(只改 build 行为)

### 风险
- BuildKit 必须启用:确认 `DOCKER_BUILDKIT=1` 或 docker compose v2 自带(本项目用 `docker compose -f ...`,v2 默认启用 BuildKit · 应已 OK)
- pnpm cache mount 需路径在 alpine 上验证(默认 `/root/.local/share/pnpm/store`)
- 国内镜像万一某个依赖未同步可加 `--extra-index-url` 兜底

---

## 2. 坑 2 · build 静默 12-30 分钟无输出 → 30min hard timeout 被动等

### 现状
- `update.sh:166` · `$COMPOSE up -d --build --force-recreate --no-deps "${RECREATE_SVCS[@]}" 2>&1 | tail -40`
- `tail -40` 把整个 build 输出**缓冲到结束才打印** · build 期间 GitHub runner 收到的 stdout 是 0 行
- `gh run view --log` 在 in-progress 时**不返回任何日志**(GitHub API 限制)· 排错完全被动
- `deploy.yml:25` · `timeout-minutes: 30` · 是部署 job 总超时 · 不是单步 docker build 超时

### 修复选项

#### A · docker build 主动超时 + 失败时诊断输出(推荐 · 主动止血)
```bash
# update.sh · 3/6 步骤
if ! timeout 900 $COMPOSE up -d --build --force-recreate --no-deps "${RECREATE_SVCS[@]}"; then
  echo "❌ docker build 超 15min · 主动失败 · 诊断输出:"
  df -h /var/lib/docker
  docker system df
  docker ps -a
  ps aux | grep -E "(docker|buildx)" | head
  exit 1
fi
```
- 15 分钟主动失败,留 5-10 分钟给后续步骤(alembic / healthcheck)· 配合 GitHub 30min 余量
- 失败时自动输出"为什么卡"的诊断信息

#### B · build 实时流式输出(推荐 · 反馈友好)
```bash
$COMPOSE up -d --build --progress=plain --force-recreate --no-deps "${RECREATE_SVCS[@]}"
# 不再 | tail -40 · 让 BuildKit 的 plain progress 流式回写到 SSH stdout
```
- `--progress=plain` 让 BuildKit 输出行式(非交互 TTY 进度条)· 实时流到 SSH stdout
- 移除 `tail -40` 缓冲 · GitHub runner 实时看到每一行(`STEP 5/10 · pip install...`)
- 没有 build 静默的诊断盲区

#### C · 失败时自动诊断输出(推荐 · 不只是 build,所有失败都加)
```bash
# update.sh · 现有 trap 'on_err' ERR 扩展
on_err() {
  ...
  echo "── 失败时诊断 ──"
  df -h /var/lib/docker | head -3
  docker system df 2>/dev/null
  $COMPOSE ps 2>/dev/null
  exit 1
}
```

#### 推荐:A + B + C 都做
- A · 主动止血 · 不再等 30min
- B · 实时反馈 · 中途排错有信号
- C · 失败时自动收集诊断信息 · 不靠人工 SSH

### 改动范围 + 生效路径
- 文件:`update.sh`(3 处:3/6 docker build + on_err + 也可加到 4/6 alembic 健康等待循环)
- 生效路径:**update.sh 改动需先部署一次才生效**(它从 git 拉取 · 鸡生蛋问题 · 详见末尾"生效路径总表")
- 同期 `deploy.yml:25` `timeout-minutes: 30` 可下调到 `15`(因为有主动超时,30 分钟不再需要)· 但保守一点先不动

### 风险
- `timeout 900` 是 GNU coreutils · Linux 标配 · VPS 已有(不是 macOS 的问题)
- `--progress=plain` 在某些 docker compose 版本可能要 `BUILDKIT_PROGRESS=plain` env · 现场验证

---

## 3. 坑 3 · builder cache 无自动清理 → 堆 30GB 拖死 build

### 现状
- 部署流程**完全没有清理逻辑**
- 历次 build 累积:每次部署后 builder cache 增长 ~200MB-1GB · 几个月堆到 30GB
- 30GB 时 `docker build` IO 拖累 + 元数据查询慢 · 直接卡死

### 修复选项

#### A · update.sh 部署成功后温和清理 7 天前(推荐 · 跟节奏对齐)
```bash
# update.sh · 6/6 健康检查通过后(最末尾)
banner "7/7 · 清理 7 天前的 builder cache(温和保留近期可复用)"
docker builder prune -f --filter "until=168h" 2>&1 | tail -5
ok "builder cache 已清(保留 7 天内可复用 cache)"
```
- 时机:**部署成功后**(此时无 build 在跑、新容器已 healthy · 与运行容器无冲突)
- 策略:`until=168h` = 7 天前的 cache 删 · 保留最近 7 天的让下次 build 还能复用层缓存
- 跟坑 1 的 pip cache mount 互补:pip wheel 由 BuildKit 管 · Dockerfile 层 cache 由 prune 管
- 失败不影响部署(`|| true` 兜底)

#### B · 独立 cron 每周清(与部署解耦)
- 服务器 `/etc/cron.weekly/docker-prune.sh` · 每周日凌晨清 · 跟部署无关
- 优点:不影响部署链路;缺点:多一个服务器侧配置点

#### C · BuildKit GC 配置 daemon.json(根治)
```json
{
  "builder": {
    "gc": {
      "enabled": true,
      "defaultKeepStorage": "20GB",
      "policy": [
        {"keepStorage": "20GB", "filter": ["unused-for=168h"]}
      ]
    }
  }
}
```
- 让 BuildKit 自身在超过 20GB 时自动 GC · 最优雅
- 改 docker daemon 配置需 `systemctl restart docker` · 一次性运维操作

#### 推荐:A + C 组合
- A 让部署流程自带"清理",可见可控
- C 是 docker daemon 的兜底机制(即使 update.sh 没跑 cleanup 也不会失控)
- B 不推荐(碎片化 · 失败时无 audit trail)

### 改动范围 + 生效路径
- A:`update.sh` 末尾加 7/7 步骤 · update.sh 改动 → 下次部署生效
- C:服务器 `/etc/docker/daemon.json` + `systemctl restart docker` · **产品方一次性运维**(不依赖部署链)

### 风险
- A 的 `prune --filter until=168h` 对运行容器**无影响**(只清未引用的 builder cache);跟产品方 #57 后手动 prune 触发"rw layer snapshot not found"不同 —— 那次是因为某些被引用的层意外被回收,这次过滤 7 天前就避开
- C 重启 docker daemon 会让所有容器短暂停转 · 选服务低峰执行(夜间)
- 安全核对:`docker builder prune` 默认不动有引用的容器 cache · 但仍建议**只在部署成功后(无 build 在跑时)清**

---

## 4. ⚠️ 坑 4 · update.sh 用 git HEAD 判版本 = 三向脱钩盲区

### 现状
`update.sh` 两处 fast-exit 判断:
1. **1/6**:`if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then ... exit 0; fi` → "已是最新版本"
2. **2/6**:`git diff --name-only OLD..NEW` 全空 / 全 docs/scripts → "无需重建"
3. **2/6**:alembic 检测 `--diff-filter=A` 只看新增 .py · 已在历史的迁移文件不再算"新"

三个判断的共同盲点:**只信 git 文件状态,不查 docker image / DB schema 的实际状态**。

当 git HEAD 已推进但 image 没换 / DB 没迁移时(脱钩态),三个判断**全部误判** → 假绿。

### 修复选项

#### A · `FORCE_REBUILD=1` 环境变量绕开所有快速路径(推荐 · 立即可用)
**deploy.yml 改 + update.sh 改 · 两份配合**:
```yaml
# deploy.yml
on:
  workflow_dispatch:
    inputs:
      force_rebuild:
        description: '强制完整重建(绕开 git diff 判定 · 紧急救场用)'
        type: boolean
        default: false
  push: {branches: [main]}

jobs:
  deploy:
    steps:
      - name: SSH 到服务器 · git checkout main + update.sh
        run: |
          ssh ... "cd /opt/midas && git fetch origin && git checkout -f main && \
            FORCE_REBUILD='${{ inputs.force_rebuild || 'false' }}' bash update.sh"
```
```bash
# update.sh
FORCE_REBUILD="${FORCE_REBUILD:-false}"
if [ "$FORCE_REBUILD" != "true" ]; then
  if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
    echo "已是最新版本 ..."  # 现有快速路径
    exit 0
  fi
else
  warn "FORCE_REBUILD=true · 跳过快速路径,强制完整重建 api/worker + alembic"
  NEED_BUILD_API=true
  NEED_COMPOSE_UP=true
  NEED_ALEMBIC=true
fi
```
- 用户在 GitHub UI dispatch 时勾选 "force rebuild" 即可走完整路径
- 救场场景明确:image/DB 跟 git HEAD 脱钩时,FORCE_REBUILD=true 一键恢复
- **鸡生蛋**:第一次部署 FORCE_REBUILD 改动时,update.sh 还没读 env(因为 git 仓库里 update.sh 还是旧版)· 但 deploy.yml 改了能传 env · update.sh 收到但忽略 · 第一次"普通"部署后 update.sh 就是新版了 · 之后 dispatch 勾 force_rebuild 才生效

#### B · docker image 时间戳 vs git HEAD 智能检测(更智能)
```bash
# update.sh
IMG_BUILD_SHA=$(docker inspect midas-api --format='{{ index .Config.Labels "git.sha" }}' 2>/dev/null)
if [ -n "$IMG_BUILD_SHA" ] && [ "$IMG_BUILD_SHA" != "$NEW_HEAD_SHORT" ]; then
  warn "image label git.sha=$IMG_BUILD_SHA ≠ 当前 HEAD=$NEW_HEAD_SHORT · 强制重建"
  NEED_BUILD_API=true
fi
```
配合 Dockerfile 加 `LABEL git.sha=<head>` build arg。
- 每次 build 在 image 打 git sha label
- 启动时对比 label vs git HEAD · 不一致就强制重建
- **不能根治** alembic 部分(image 一致不代表 DB schema 跟 alembic head 一致)
- 复杂度更高 · 但智能

#### C · alembic 自愈检查(护最关键的边)
```bash
# update.sh · 不管前面判定如何,最后总跑一次:
CURR_HEAD=$(docker exec midas-api alembic current 2>&1 | grep -v "^INFO\|^$" | tail -1 | awk '{print $1}')
LATEST_HEAD=$(ls apps/api/alembic/versions/*.py | xargs grep -l "down_revision = None\|^revision = " | ... ) # 算出代码里 alembic head
if [ "$CURR_HEAD" != "$LATEST_HEAD" ]; then
  warn "DB head=$CURR_HEAD ≠ code head=$LATEST_HEAD · 强制 alembic upgrade"
  docker exec midas-api alembic upgrade head
fi
```
- 部署最末尾兜底:不管前面 NEED_ALEMBIC 怎么算,最后总验证一次实际 DB head
- 不一致就跑 upgrade(幂等 · 已最新就 no-op)
- 单纯保护 DB schema 的边 · 不护 image 的边

#### 推荐:A 立即做 + B/C 第二阶段
- **A 是最实用的救场开关**(N1 故障如果有 FORCE_REBUILD,不用产品方 SSH reset 也能恢复)
- **B 是优雅的智能检测**(无人值守时自愈,但复杂度高,要权衡)
- **C 是 alembic 单点保险**(对齐 0010 数据精度的"DB 边总要查"教训)

### 改动范围 + 生效路径
- **A**:
  - `deploy.yml` 加 `inputs.force_rebuild`(独立改 · push main 即生效)
  - `update.sh` 读 FORCE_REBUILD env(改动后第一次普通部署上线)
  - 鸡生蛋:`deploy.yml` 改动后即使 `update.sh` 旧版,dispatch 传 env 也无害(旧版 update.sh 忽略 env);第一次普通部署后 update.sh 新版生效 · 之后 dispatch 勾 force_rebuild 才真生效。**所以建议**:deploy.yml + update.sh 同一个 commit 里改,普通 push 上线 → 之后 force_rebuild 开关可用
- **B**:Dockerfile + update.sh 同期改 · 第一次部署后(image label 写入)生效
- **C**:update.sh 改 + 找一个稳定算 latest_head 的方法(读 alembic env.py · 不依赖 docker)· 下次部署生效

### 风险
- A 的 inputs 在 push trigger 下没有(只 dispatch 才有)· 加 `${{ inputs.force_rebuild || 'false' }}` 默认 'false'
- B 的 image label 在第一次部署有 label 之前 inspect 返回空 · 兜底:label 空时也走完整路径(更保守)

---

## 5. ⚠️ 坑 5 · 中途失败留下 git HEAD 推进 / image+DB 没换 = 三向脱钩

### 现状
`update.sh` 第 1 步:
```bash
git fetch origin main
git reset --hard origin/main   # ← git HEAD 立刻推进到新 commit
# 后续步骤(build/alembic)失败时,git HEAD 不回滚
```

被 timeout 砍 / build 失败时 git HEAD 已经在新 commit,但 image / DB 还在旧状态。下次部署 update.sh 用新的 git HEAD 当 OLD,后续 diff 永远看不到"未应用"的改动 → 连环误判。

### 修复选项

#### A · `git reset` 放在所有步骤成功之后(最彻底)
```bash
# update.sh
# 1/6 改为:git fetch(不 reset) + 用 origin/main 作 NEW_HEAD 做 diff
# 中间所有 build/alembic 用 worktree checkout 临时目录 · 不改 git HEAD
# 6/6 健康检查通过后:git reset --hard origin/main
```
- 思想:**git HEAD 是部署成功的标记 · 不是部署开始的标记**
- 改动较大 · 现有 `git diff OLD..NEW` 逻辑要换成 `git diff OLD..origin/main`
- 风险:worktree 目录管理 + docker build context 路径要适配

#### B · `trap ERR` 时回滚 git HEAD(轻量补丁)
```bash
# update.sh
OLD_HEAD_SAVED=""
on_err() {
  ...
  if [ -n "$OLD_HEAD_SAVED" ]; then
    echo "${YELLOW}↩ 回滚 git HEAD 到 $OLD_HEAD_SAVED · 防止三向脱钩${NC}"
    git reset --hard "$OLD_HEAD_SAVED" 2>&1 | tail -1
  fi
  ...
}

# 1/6 改:
OLD_HEAD_SAVED=$(git rev-parse HEAD)   # 先存
OLD_HEAD=$OLD_HEAD_SAVED
git fetch origin main
git reset --hard origin/main           # 推进
```
- 改动小(1 行 trap + 1 行 save)
- 失败时 git HEAD 回到部署前 · 重试时 update.sh 用对的 OLD
- **仍可能**部分失败(build 成功 alembic 失败)留下 image 已新 / DB 旧的脱钩 · 需配合坑 4 的 alembic 自愈(C)兜底

#### C · git checkout 延后到末尾(改动中等)
- 1/6 只 `git fetch` · 不 checkout
- 用 `origin/main` 做 NEW_HEAD · 所有 build 在 `git worktree` 临时目录 / `git archive` 临时解压
- 6/6 成功后 `git checkout -f main`(让 working tree 跟 origin 同步)
- 比 A 轻量 · 比 B 安全 · 但实施复杂

#### D · Actions 自动 trigger 回滚 workflow(更复杂)
- 部署失败时 GitHub Actions 自动触发 "rollback" workflow,执行 SSH git reset 到上一个 success deploy 对应的 sha
- 需新增 workflow + 跟踪 last-success commit · 不推荐(现阶段杀鸡用牛刀)

#### 推荐:B(立即做,补 1 行 trap)+ 长期演进到 A 或 C
- B 是 patch · 1-2 行就能挡住"git HEAD 脱钩"
- A/C 是结构改 · 大改 update.sh · 留下次单独迭代

### 改动范围 + 生效路径
- B:`update.sh` 改 trap + 改 1/6 · update.sh 改动 → 下次部署生效

### 风险
- B 不防"build 成功 alembic 失败" → image 新 / DB 旧 · 此时 git HEAD 已 reset 回旧 commit → 下次部署 OLD=旧 NEW=新,update.sh 看到 N1 改动重新跑 build + alembic → **自愈**(image 已新 build 会命中 cache 很快)
- A/C 改动大,需要单独一期工程对齐

---

## 6. 改动生效路径总表(鸡生蛋关键)

| 坑 | 改动文件 | 是否 git 拉取链(update.sh)| 生效路径 |
|---|---|---|---|
| 1 · pip cache | Dockerfile × 3 | ✅ git 拉 | **下次 build** 生效(部署 → git pull → 下次 build 用新 Dockerfile) |
| 2 · 静默护栏 | update.sh | ✅ git 拉 · **鸡生蛋** | 第一次部署 update.sh 自身改动:**该次部署仍用旧 update.sh** · 之后部署用新 update.sh 才有护栏 |
| 3A · 部署后清缓存 | update.sh | ✅ git 拉 · **鸡生蛋** | 同上 |
| 3C · BuildKit GC | `/etc/docker/daemon.json` | ❌ 服务器侧 | **产品方一次性 SSH 改 + restart docker** · 跟部署链解耦 · 立即生效 |
| 4A · FORCE_REBUILD | deploy.yml + update.sh | deploy.yml ❌ / update.sh ✅ | deploy.yml 改后 push main 即生效;update.sh 改后下次部署生效;**两文件一个 commit 改 + 普通 push 上线** · 之后 force_rebuild 开关可用 |
| 4B · image label | Dockerfile + update.sh | ✅ ✅ | 第一次部署 image 才有 label · 之后部署 update.sh 才能读 label 比对 |
| 4C · alembic 自愈 | update.sh | ✅ | 下次部署生效 |
| 5B · trap 回滚 | update.sh | ✅ · **鸡生蛋** | 第一次部署 update.sh 自身改动:**该次部署如果失败,trap 不会回滚**(旧 update.sh 无此逻辑);之后部署有保护 |

### 上线节奏建议
- **第一波**(立即):坑 1A+C(Dockerfile)+ 坑 2A+B+C(update.sh)+ 坑 3A(update.sh)+ 坑 4A(deploy.yml + update.sh)+ 坑 5B(update.sh)→ **一个 commit · push main · 一次部署**
  - 该次部署仍用旧 update.sh,但因 Dockerfile 改了,build 会用新规则 · 改善 pip cache 是该次直接受益
  - update.sh 改动该次没生效 · 但**下次部署起**所有 update.sh 改动(静默护栏 / 部署后清缓存 / FORCE_REBUILD / git 回滚)全部生效
- **第二波**(运维):坑 3C BuildKit daemon.json · 产品方一次性 SSH · 跟部署解耦

---

## 7. 决策点(需产品方拍板 · 逐条单列)

**DP1 · pip 缓存方案**:
1. ① **A + C 组合**(BuildKit cache mount + PyPI 国内镜像 · 推荐)
2. ② 只做 A(cache mount · 改 Dockerfile · 不动镜像源)
3. ③ 只做 C(改镜像源 · 不引入 BuildKit cache)
4. ④ 都不做 · 保守

**DP2 · build 静默护栏**:
1. ① **A + B + C 全做**(主动 timeout + 流式输出 + 失败时诊断 · 推荐)
2. ② 只做 A(主动 timeout)
3. ③ 只做 B(流式输出)

**DP3 · builder cache 清理策略**:
1. ① **A + C 组合**(update.sh 部署后温和清 + BuildKit GC 兜底 · 推荐)
2. ② 只做 A(update.sh 部署后清)
3. ③ 只做 C(BuildKit GC 配置)
4. ④ 都不做 · 出问题手动清

**DP4 · 三向脱钩防护**:
1. ① **4A FORCE_REBUILD + 5B trap 回滚**(轻量 + 救场开关 · 推荐)
2. ② 加 4C alembic 自愈(护 DB schema 边)
3. ③ 加 4B image label 智能检测(智能但复杂)
4. ④ 长期演进到 5A/5C(git checkout 延后)· 大改

**DP5 · BuildKit GC defaultKeepStorage 阈值**(如 DP3 选 ① 或 ③):
1. ① 20GB(保守 · 让 cache 多保留点提升命中)
2. ② 10GB(更紧 · 防爆磁盘)
3. ③ 30GB(宽松 · 接近本次事故的临界点 · 不推荐)

**DP6 · update.sh 改动是否捆绑成一个 commit 还是分多个 commit**:
1. ① **一个 commit 全做**(原子上线 · 推荐)
2. ② 分多个 commit(每个坑独立 · 便于回滚单条)

**DP7 · `deploy.yml timeout-minutes` 是否下调**(若 DP2 加了 docker build 主动 timeout):
1. ① 保持 30 分钟(留余量 · 推荐)
2. ② 下调到 20 分钟(更激进失败检测 · 配合主动 timeout)

---

## 8. 实施分期建议(产品方拍板后)

按推荐组合(DP1①+DP2①+DP3①+DP4①+DP5①+DP6①):

**N1 · Dockerfile + deploy.yml + update.sh 一波改 · 一个 commit · push main**(后端无业务改动)
- `apps/api/Dockerfile` · `apps/worker/Dockerfile`:加 `RUN --mount=type=cache,target=/root/.cache/pip pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple`(去掉 --no-cache-dir)
- `apps/web/Dockerfile`(可选):pnpm store cache mount
- `update.sh`:
  - 3/6 步骤 docker build 包 `timeout 900` + `--progress=plain` 流式
  - 6/6 之后加 7/7 步骤 `docker builder prune -f --filter "until=168h"`
  - `trap on_err ERR` 加 `git reset --hard $OLD_HEAD_SAVED`
  - 1/6 加 `OLD_HEAD_SAVED=$(git rev-parse HEAD)` 在 fetch 之前
  - 读 `FORCE_REBUILD` env,绕开 1/6 + 2/6 快速路径(强制走完整路径)
- `deploy.yml`:加 `inputs.force_rebuild` boolean default false,SSH 命令前置 `FORCE_REBUILD='...'`

**N2 · 服务器一次性运维**(产品方做)
- 写 `/etc/docker/daemon.json` 加 BuildKit GC 配置(DP5 选项)
- `systemctl restart docker`(夜间低峰执行)

**N3 · 验证**
- 故意触发一次 dispatch + `force_rebuild=true` → 验证强制路径走通
- 看 build 时间是否从 ~40min 降到 ~3-5min(pip cache mount 生效)
- 看 update.sh 末尾打印 prune 数据

**长期 backlog**(本期不做)
- 坑 4B image label 智能检测
- 坑 4C alembic 自愈
- 坑 5A/5C git checkout 延后(大改)

---

## 9. 风险点 + 测试覆盖思路

### 风险
- BuildKit cache mount 在 docker compose v1 不支持 · 确认服务器 docker compose 是 v2(本项目用 `docker compose -f ...` v2 命令式 · 应已满足)
- `timeout 900` 跟 docker daemon 之间:timeout 把 shell 进程砍掉 · docker daemon 内部 build job 可能继续 · 留下"半成品 build"。 缓解:trap 里加 `docker buildx prune --keep-storage 1GB` 或直接 reset · 但这是次生问题
- update.sh 内 `git reset --hard $OLD_HEAD_SAVED` 失败时(磁盘满 / 权限错)on_err 会再被 trap 触发递归 · 加 `trap - ERR` 在 on_err 入口防递归

### 测试覆盖(部署侧 · 不是 pytest 矩阵)
- N1 改动 push main 部署本身就是测试 · 看 build 时间 + 看 update.sh 末尾 prune 数据
- 故意 dispatch force_rebuild=true · 验证 FORCE_REBUILD 路径
- 故意制造一个 build 失败场景(改 Dockerfile 加 `RUN false`)· 验证主动 timeout / trap 回滚 / 失败诊断输出 → 完了再 revert(本测试在 staging 做最好,但项目无 staging,谨慎)

---

## 10. 一句话总结

**N1 故障攒齐 5 坑;一波部署同时打掉 4 + 服务器一次性运维收尾 BuildKit GC;FORCE_REBUILD 是救场总开关。下次再三向脱钩,GitHub UI 勾一下就恢复,不用产品方 SSH。**
