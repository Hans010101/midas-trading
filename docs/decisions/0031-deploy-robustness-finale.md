# ADR 0031 · 部署健壮性收尾 · fast-path 误判修复 + web cache mount

**Status**: Approved · 2026-05-28
**Owner**: Claude Code(产品方审通过 DP1-DP5)
**Related**: 0029(部署健壮性 N1+N2)· 0030(字体本地化)· closes #293 / #282 · holds #273

---

## 1. 背景:一天部署 ordeal 留下的三个尾巴

ADR 0029 N1+N2 + 0030 字体本地化把"部署链路 5+1 个坑"治本了。但剩三个尾巴需要收口:

- **#293(P1)fast-path 误判** · 一天三次部署(N2/字体/N3)都被迫 push 两次:第一次 push 走 fast-path 不重建,第二次 force_rebuild=true 才真重建
- **#273(后续待办)拆 midas-api-base 镜像** · 若 keepStorage 后仍冷启动 build 时启动
- **#282(后续待办)web Dockerfile 加 BuildKit cache mount** · pnpm store + .next/cache

这是改部署流程本身,改错影响所有后续部署。每条改动的【生效路径 + 验证方法】都要说清。

---

## 2. 根因 · fast-path 误判(#293)

### 2.1 故障链复盘(三层叠加)

```
0029 N1 hotfix-1(commit 0b0c98c):
  update.sh `--progress=plain` flag bug → 失败 → trap 回滚

0029 N1 hotfix-2(commit 2fc1c21):
  deploy.yml SSH cmd 改:`git checkout -f main` → `git reset --hard origin/main`
  动机:让 update.sh 改动【立即生效】(不再滞后一次部署)
  副作用:server local main HEAD 在 update.sh 启动【之前】就被强行同步到 origin/main

0029 N1 hotfix-3(commit 39bd6c9):
  update.sh `timeout 900 → 1500`(给 build 充足时间)

后果(本 ADR 修复对象):
  update.sh 1/7 步骤:
    OLD_HEAD = $(git rev-parse HEAD)     # 已等于 origin/main(因 deploy.yml reset)
    git fetch origin main                # 无变化(同 commit)
    NEW_HEAD = $(git rev-parse origin/main)
    OLD_HEAD == NEW_HEAD                 # ★ 永真!
    → "已是最新版本 · exit 0"            # ★ fast-path 误判
```

### 2.2 为什么是"误判"

普通用户场景:
- 推 commit X 到 main(代码改动)
- deploy.yml 触发
- server local main was Y(上次部署 commit)
- **应该重建**(因为 Y → X 有代码改)

但 hotfix-2 让 SSH 命令在调 update.sh 前已 `git reset --hard origin/main` → server local main 从 Y 跳到 X → update.sh 1/7 看 HEAD 已是 X → fast-path → 不重建。

**Bug 本质**:diff 判定基于"git HEAD 是否变化",而 hotfix-2 已经强制变化(reset)。

---

## 3. 决策表(DP1-DP5 · 产品方拍板)

| DP | 决策 | 选择 | 理由 |
|---|---|---|---|
| **DP1** | #293 修法 | **B · deploy.yml 算 OLD_HEAD/NEW_HEAD 传 env + update.sh 读 env + fallback** | 改 2 文件 · 不动 Dockerfile/compose · 沿用现有 diff 判定 · 生效路径已实证 |
| **DP2** | #273 拆 base 镜像 | **不做 · 列触发条件** | N2 keepStorage 后 cache 稳定 22GB · 没必要 · 复杂度高 |
| **DP3** | #282 web cache mount | **做** | 对齐 api/worker 模式 · 改动小 · 风险低 |
| **DP4** | 合并策略 | **单 commit 三改动一起做** | 同次部署即生效 · 减少 CI 次数 |
| **DP5** | 验证策略 | **跑四场景全过才算修好** | 防"修一个 bug 引入反向问题" |

---

## 4. 改动设计

### 4.1 #293 修法 B(deploy.yml + update.sh)

#### deploy.yml SSH 命令(改前)
```
"cd /opt/midas && git fetch origin main && git checkout main && git reset --hard origin/main && FORCE_REBUILD='${{ inputs.force_rebuild }}' bash update.sh"
```

#### deploy.yml SSH 命令(改后)
```
"cd /opt/midas && OLD_HEAD=\$(git rev-parse HEAD) && git fetch origin main && git checkout main && git reset --hard origin/main && NEW_HEAD=\$(git rev-parse HEAD) && OLD_HEAD=\$OLD_HEAD NEW_HEAD=\$NEW_HEAD FORCE_REBUILD='${{ inputs.force_rebuild }}' bash update.sh"
```

关键点:
- 在 `git reset --hard origin/main` **之前**算 `OLD_HEAD`(server 本地的旧 HEAD)
- 在 reset **之后**算 `NEW_HEAD`(已同步到 origin/main)
- 两个一起 export 给 `bash update.sh` 作 env
- `\$(...)` 转义防 GitHub Actions YAML 在写入命令时被本地展开(命令字符串包在 `"..."` 里,内层 `$(...)` 需要在远端 bash 执行,而非本地 GH Actions 解析时执行)

#### update.sh 1/7 改造

```bash
# ── ADR 0031 · DP1 · fast-path 修复 ──
# 优先用 deploy.yml 传入的 env(已知 reset 前 OLD_HEAD)
# env 为空时退化到从 disk 自算(向后兼容手动 SSH 跑 `bash update.sh` 场景)
OLD_HEAD_SRC="env"
NEW_HEAD_SRC="env"
if [ -z "${OLD_HEAD:-}" ]; then
  OLD_HEAD="$(git rev-parse HEAD)"
  OLD_HEAD_SRC="disk"
fi
git fetch origin main 2>&1 | tail -3
if [ -z "${NEW_HEAD:-}" ]; then
  NEW_HEAD="$(git rev-parse origin/main)"
  NEW_HEAD_SRC="disk"
fi

# ⚠️ banner 提示来源 · 手动跑场景一眼看出"env 未注入·走 disk 自算"
[ "$OLD_HEAD_SRC" = "disk" ] && warn "OLD_HEAD env 未注入 · 从 disk 自算 = ${OLD_HEAD:0:8}(手动 SSH 跑 · 可能触发 fast-path 误判)"
[ "$NEW_HEAD_SRC" = "env"  ] && echo "  OLD_HEAD/NEW_HEAD 来自 deploy.yml env(reset 前/后)"

echo "  OLD_HEAD = ${OLD_HEAD:0:8} · NEW_HEAD = ${NEW_HEAD:0:8}"
```

### 4.2 web Dockerfile cache mount(#282)

#### 改前
```dockerfile
FROM node:20-alpine AS builder
...
RUN pnpm install --frozen-lockfile
...
RUN cd apps/web && pnpm build
```

#### 改后
```dockerfile
# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS builder
...
# pnpm store 缓存(tarball 复用 · 不写入镜像层)
RUN --mount=type=cache,target=/root/.local/share/pnpm/store,sharing=locked \
    pnpm install --frozen-lockfile
...
# Next.js .next/cache 增量编译(rebuild 显著提速 · sharing=locked 跟 api 一致)
RUN --mount=type=cache,target=/repo/apps/web/.next/cache,sharing=locked \
    cd apps/web && pnpm build
```

预期效果:
| 阶段 | 改前 | 改后(rebuild) | 改后(首次/cache 空) |
|---|---|---|---|
| pnpm install | ~30-60s | ~5-10s | ~30-60s |
| next build | ~4-5min | ~1-2min | ~4min |
| 整体 web | ~5-6min | ~2-3min | ~5min |
| force_rebuild 三服务总 | 11-14min | 6-9min(cache 满) | 11-14min(首次) |

---

## 5. 生效路径速查表

| 改动 | 文件 | 生效路径 | "鸡生蛋"? |
|---|---|---|---|
| #293 deploy.yml 算 OLD_HEAD | `.github/workflows/deploy.yml` | **本次 push 立即生效** · GH Actions 用 trigger commit 的 workflow file | ❌ 无 |
| #293 update.sh 读 env + fallback | `update.sh` | **本次 push 立即生效** · 2fc1c21 hotfix 已让 `git reset --hard` 把 disk update.sh 同步到 origin/main 版本 | ❌ 无 |
| #282 web Dockerfile cache mount | `apps/web/Dockerfile` | **下次部署立即生效** · BuildKit 读新 Dockerfile | ❌ 无 |

⭐ 三改一起 push 后,**单次部署即全部生效**。

---

## 6. ⭐ DP5 · 验证设计(防反向退化)

修完后必须跑四个场景,每个都符合期望,才算修好。

### 场景 ① · docs-only push(不应触发 deploy)

**操作**:在 feature 分支以外的 commit,改 `docs/decisions/0031-*.md`(已在 paths-ignore)
**期望**:GitHub Actions **不触发** deploy(`paths-ignore: docs/**` 已挡)
**验证**:`gh run list --workflow=deploy.yml --limit 1` 看不到新 run

### 场景 ② · ⭐ 普通代码 push(必须真重建,不再 fast-path 误判)

**操作**:推一个 `apps/api/*` 的小代码改动(改一行注释)到 main
**期望**:
- 触发 deploy
- update.sh banner 1/7 显示 `OLD_HEAD/NEW_HEAD 来自 deploy.yml env`
- **OLD_HEAD ≠ NEW_HEAD**(因为 OLD_HEAD 是 reset 前,server 还停在上一次 commit)
- 2/7 看到 `apps/api/` 改动 → `NEED_BUILD_API=true`
- 3/7 force-recreate api/worker
- 不再走 "已是最新 · exit 0"
- build 时间几分钟级(BuildKit cache 满命中,api pip CACHED,web pnpm/next CACHED)

**这是本 ADR 修复成功的核心实证**。

### 场景 ③ · workflow_dispatch + force_rebuild=true(强制重建仍有效)

**操作**:GitHub Actions 页面手动 trigger,勾 force_rebuild
**期望**:
- update.sh banner 1/7 警告 `FORCE_REBUILD=true · 跳过 fast-path`
- 不论 HEAD 是否变化,2/7 走 `FORCE_REBUILD=true · 忽略 diff · 强制重建 api + worker + web`
- 3/7 force-recreate 三服务

### 场景 ④ · workflow_dispatch 不勾 force_rebuild(真 fast-path 仍有效)

**操作**:GitHub Actions 页面手动 trigger,**不勾** force_rebuild(也没有新 push)
**期望**:
- update.sh banner 1/7 显示 `OLD_HEAD == NEW_HEAD`(server HEAD 跟 origin/main 一致)
- 走 "已是最新版本 · exit 0" fast-path
- 用时 ~25s(健康检查 + 退出)

**意义**:确认 fast-path 在"真无变化"时仍能用,没被反向破坏。

### 期望矩阵(对照表)

| 场景 | 触发 deploy | 真重建 | banner 1/7 | build 时间 |
|---|---|---|---|---|
| ① docs-only push | ❌ | — | — | — |
| ② 代码 push | ✅ | ✅ | `OLD≠NEW · env 来源` | 几分钟级 |
| ③ dispatch + force_rebuild | ✅ | ✅(强制三服务) | `FORCE_REBUILD=true 跳过 fast-path` | 几分钟级 |
| ④ dispatch 无 force_rebuild | ✅ | ❌ | `OLD==NEW · 已是最新` | ~25s |

---

## 7. 红线 + 风险

### 红线(本 ADR 实施期严守)
- ✅ update.sh fallback 必须正确(env 为空时退化到现有逻辑,不破坏手动 SSH 跑场景)
- ✅ deploy.yml SSH 命令 bash 引号转义严格核对(防再现 --progress flag 类 typo)
- ✅ web Dockerfile cache mount 路径准确(pnpm store / .next/cache)
- ✅ 视觉零回归(对照 0030 字体本地化的严谨度,build 产物体积对照)
- ✅ ⭐ **绝不能反向退化** — 修完后【普通代码 push 一次就真重建】+ 【无改动/docs-only 仍走快速通道】

### 风险
| 风险 | 缓解 |
|---|---|
| deploy.yml YAML 引号嵌套出错 | 用 `\$(...)` 防 GH Actions 本地展开 · 本地 `yamllint` 检查 + 手 review |
| update.sh 加 env 退化逻辑写错 | 严格 `${VAR:-default}` 模式 · 加 banner 提示来源 · 手动 SSH 场景兼容 |
| web Dockerfile cache mount 路径错 | 对齐 api/worker 已实证 sharing=locked 模式 · pnpm 官方文档确认 store 默认位置 |
| 视觉回归 | 本地 `pnpm build` 字节级体积对比改前 |
| 反向退化(每次都全量重建 14min) | DP5 场景 ④ 必跑(确认 fast-path 仍能在"真无变化"时生效) |

---

## 8. ADR 状态收口

| 关联 task | 状态 |
|---|---|
| #293 fast-path 误判 | ⭐ **本 ADR 修复 · 关闭** |
| #282 web cache mount | ⭐ **本 ADR 实施 · 关闭** |
| #273 拆 base 镜像 | **保持 pending · 列触发条件** |

### #273 触发契约(if X then Y)

只在以下任一情况触发 #273 启动:
- 服务器换机 / 重装 docker daemon(BuildKit cache 必丢)
- 实战再次出现冷启动 build ≥ 30min
- daemon.json keepStorage 配置失效(GC 把 cache 清到 < 5GB)

---

## 9. 一句话总结

**fast-path 误判 = 2fc1c21 hotfix 让 git HEAD 在 update.sh 启动前已等于 origin/main · diff 判定恒空。修法 = deploy.yml 在 reset 前算 OLD_HEAD 传 env · update.sh 读 env(空则 fallback)· DP5 四场景验证防反向。**
