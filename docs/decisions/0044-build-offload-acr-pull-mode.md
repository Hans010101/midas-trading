# ADR 0044 · 部署基建根治:build 挪出 VPS → Actions build+push ACR → VPS 只 pull

- 状态:**Accepted**(产品负责人 Hans 2026-07-04 拍板;阶段1-4 分批实证收官)
- 日期:2026-07-04
- 相关:0033(自验吞退出码 · 部署成功判定)· `deploy-build-memory-wall` / `deploy-sequential-build-fix` /
  `deploy-traps-adr0033`(memory)· `.github/workflows/deploy.yml` · `update.sh` · `docker/docker-compose.yaml`

## 背景(实证 · 三次翻车)

7G 香港 VPS 跑**全部**生产容器(web768M/api1G/worker256M/pg768M/ch2G/redis256M · 静息仅 ~2.6G avail),
旧部署链在**同一台机器**上再跑重型 `next build` → 无内存余量。i18n 批0([locale] 双语路由手术)
上线 **连翻三次**:

1. **v1 · 内存竞争**:next-intl SSG 页数翻倍(45→90)→ build 内存 × 容器内存把整机压到 000(~1h40min)。
2. **v2 · redirect loop**:next-intl `localeDetection` 让 cookie-less 客户端 `/`→307→`/` 死循环。
3. **v3 · 整机卡死**:内存修 + loop 修都对(都在 v3),但正式部署 build+recreate+容器同机 → 机器卡死到
   SSH 不可达,07:10 强制重启。★VPS「build-only 試水」过,但正式部署的额外变量(recreate + 全容器在跑)
   足以压垮。批0 代码本身没问题,**问题始终在部署基建**(同机重型 build 无安全余量)。

## 决策

**build 从 VPS 物理挪到 GitHub Actions**(runner 内存充足)→ push 阿里云 ACR 香港 →
VPS 的 `update.sh` 从「`docker compose build`」改「`docker compose pull` + `up --force-recreate`」。
整机卡死的物理根源(同机 build)消失。

### 双模式 DEPLOY_MODE(update.sh)

| 模式 | 行为 | 何时用 |
|---|---|---|
| **pull(★默认常态)** | CI 已 build 推 ACR;VPS 只 `compose pull <改动服务>:<sha>` + recreate · 零构建负载 | 所有正常 push 部署 |
| **build(兜底)** | 旧链:VPS 本地 `compose build`(顺序防 OOM · ADR #91)→ recreate | ACR/Actions 故障、或需在 VPS 本地验证某分支镜像 |

- 触发 build 兜底:GitHub Actions 手动 `workflow_dispatch → deploy_mode=build`;或服务器 `DEPLOY_MODE=build bash update.sh`。
- 阶段2 引入双模式时默认仍 `build`(现网零改);**阶段4 起默认切 `pull`**,build 退居兜底。

### 三处改造要点

- **deploy.yml**:拆两 job — ① `build-push`(matrix 并行三镜像 · gha cache · ★web 传
  `NEXT_PUBLIC_API_URL` build-arg,ADR0016 漏了整站白屏 · build 后断言 bundle 含 `api.midastrade.asia`)
  → push ACR;② `deploy`(`needs: build-push` · SSH VPS · `DEPLOY_MODE=pull`)。**tag = 全 40 位
  `github.sha`**(与 VPS `NEW_HEAD` 同 sha · pull 对得上)+ `latest`。★`build-push` 任一失败 →
  `deploy` job 不跑 → **生产纹丝不动**(旧链 #91「build 失败宕机」物理消失)。健康检查升级**严格 200 +
  redirect-loop 探测**(旧 `curl -fsS /` 放过 3xx → 漏 v2 的 loop 假绿)。
- **compose**:三服务加 `image: ${MIDAS_REGISTRY:+${MIDAS_REGISTRY}/}midas-{svc}${MIDAS_IMAGE_TAG:+:${MIDAS_IMAGE_TAG}}`
  + `build:` 段**并存**(compose build 走 build 段=dev 不破 · compose pull 走 image=prod · 命令决定行为)。
  ★默认(两变量空)= 派生名 `midas-{svc}`(现有本地镜像 · 合并到 main 不误 build)。
- **update.sh**:pull 分支 `export MIDAS_IMAGE_TAG=$NEW_HEAD` → `compose pull` → 共用的
  `up --no-build --force-recreate --no-deps`(`--no-deps` 守 pg/ch/redis 红线)。7/7 加 **pull 模式旧 sha
  镜像催收**(每 ACR repo 留最近 3 个 + latest + 在用 · 更老删 · 防磁盘涨)。

### 前置(VPS · Hans 已配)

- ACR 命名空间 **`midastrade`** · 私有 · 自动建仓。
- 公网 registry(Actions 推):`crpi-kejjqltz4vumnjmv.cn-hongkong.personal.cr.aliyuncs.com`
- VPC registry(VPS 拉 · 内网最快):`crpi-kejjqltz4vumnjmv-vpc.cn-hongkong.personal.cr.aliyuncs.com`
- GitHub Secrets:`ACR_REGISTRY`/`ACR_USERNAME`/`ACR_PASSWORD`/`ACR_NAMESPACE`;Variable `NEXT_PUBLIC_API_URL`。
- **VPS `/opt/midas/.env`**:`MIDAS_REGISTRY=<VPC registry>/midastrade`(**含命名空间 · 无尾斜杠**)· 已 `docker login`。

## 翻车与护栏(阶段3 首跑实证)

- **翻车**:VPS `.env` 漏配 `MIDAS_REGISTRY` → compose image: 的 `${MIDAS_REGISTRY:+…}` 退化成裸名
  `midas-web:<sha>` → docker 去 docker.io 找 → `pull access denied`(cryptic)。
- **根治守卫**:update.sh pull 分支在 pull 前用 `compose config` 全量解析取 web 的 `image:` 行(compose
  **真正会拉的镜像名**)做地面真相 · 不含 `/`(无 registry 前缀)即明确报错 + 给出 `.env` 应加的确切一行。
  ★**绝不查 `$MIDAS_REGISTRY` shell 变量**:它由 `.env` 提供、compose 自己读,bash 进程里本就是空的,查它必误报。
  ★用**全量 `config`**(compose v1 起通用)非 `--images`(旧版无此 flag → 空输出会误报拦截配置正确的 .env)。
- **安全模型实证**:首跑 pull 失败时 fail-safe — git HEAD 回滚、容器未 recreate、站点全程 200 纹丝不动;
  失败诊断段「关键进程」**零 buildkit** = build 物理离开 VPS 的铁证。

## 回滚三层兜底

1. `DEPLOY_MODE=build` 一行退老链(workflow_dispatch 或 SSH 环境变量)。
2. pull 旧 sha 镜像秒回(VPS 保留最近 3 个 tag · 不重 build):`MIDAS_IMAGE_TAG=<old-sha> docker compose ... up -d <svc>`。
3. Actions build 挂 → deploy job 不跑 → VPS 零影响。

## 权衡

- **取**:整机卡死物理根源消失 · 部署从「顺序 build 十几分钟」压到「pull+recreate ~45s」· build 失败不再宕机 ·
  内存墙护栏(顺序 build / prune)退居兜底不再是主路径。
- **舍**:多一跳镜像仓库(ACR)· VPS 磁盘需管理累积镜像(已加 7/7 催收护栏)· 依赖 Actions + ACR 可用性
  (故障时 build 兜底退老链)。
