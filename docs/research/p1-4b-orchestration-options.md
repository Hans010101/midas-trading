# P1-4b 前置侦察 · worker→vibe 回测触发架构方案对比(2026-06-05)

> 只读勘察 + 方案对比,**不写编排码、不改 compose、不部署**。回答:midas-worker 如何触发
> midas-vibe 跑一次 `run_backtest_job` 并收回 artifacts。

## 一、现有 compose 结构摘要

- **文件分层**:`docker/docker-compose.yaml`(base · 6 服务)+ `docker/docker-compose.prod.yaml`
  (prod overlay · 内存限额 + 不暴露端口 + 调优)+ `docker-compose.override.yaml`(**.gitignore**,
  仅服务器侧 dev,本仓库看不到)。compose spec 现代版(`name: midas`,无 `version:` 键)。
- **部署命令**(`update.sh:97`):`docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted`。
- **服务**:postgres / clickhouse / redis / api / worker / web(web 是 `self-hosted` profile)。
- **网络**:`midas-net`(bridge · name=midas-net)✅ —— 所有服务都在上面,容器内 DNS 通(host=clickhouse:8123 / redis:6379)。
- **卷**:`midas-postgres-data` / `midas-clickhouse-data` / `midas-redis-data`。**★ 当前无任何"通用共享文件卷"**(worker 与其它服务之间没有共享可写卷)。
- **内存(prod overlay)**:postgres 768M · clickhouse 2G · redis 256M · api 1G · worker 1G(`--concurrency=2 --beat`)· web 768M(不起)→ 占用 ~4.8G,**余 ~2.5G**(与你给的一致)。
- **★ worker 能力边界**(关键):
  - `apps/worker/Dockerfile` = `python:3.11-slim`,只 `pip install -e apps/api + apps/worker`(为拿 `app.*` 模块)。
  - **无 docker CLI · 无 docker.sock 挂载 · 无 vibe**(worker 全栈无任何 `/var/run/docker` 挂载,已 grep 确认)。
  - → **worker 当前根本不能 docker run / docker exec / compose run**(没 socket、没 CLI)。要它能 = 必须挂 docker.sock(= 宿主 root,安全红线)。
- **Redis 已是 Celery broker + result backend**(`CELERY_BROKER_URL=redis://redis:6379/1`,`CELERY_RESULT_BACKEND=redis://redis:6379/2`)—— 这是关键资产,见推荐方案。
- **update.sh 部署契合**:diff 决定重建 —— `apps/api`/`apps/worker` 改→重建 api+worker;`docker/*.yaml` 改→`docker compose up -d`(apply 配置)。**★ 但当前无"deploy/vibe/ 改 → 重建 midas-vibe 镜像"的规则** → 加 vibe 服务后,update.sh 需补一条镜像重建规则(P1-4b)。

## 二、块3 Celery task 的"容器调用 TODO"现状 + 契约

`apps/worker/tasks/backtest.py` `run_backtest(params: dict, user_id: str|None)`:
- **现状**:`BacktestParams(**params)` → `build_backtest_config`(早校验 period)→ `create_pending_run`(落 pending 行)→ 返回 `{backtest_run_id, status:"pending", config, note}`。
- **TODO 预设**(注释):① `config["run_dir"]/["run_id"]` 指向**共享卷**,把 config 交给 midas-vibe 跑 `run_backtest_job`(预设 `docker run --network midas-net 挂 loader+job` 或 `compose run` 一次性 job)② 容器写 artifacts → `parse_artifacts(run_dir)` ③ `persist_result`/`persist_error`。
- **入参出参契约已定**:入 = BacktestParams 字段 dict;config = `build_backtest_config` 产出(codes/start/end/source/interval/engine/initial_cash/leverage/sma_fast/sma_slow);出 = artifacts 在 run_dir(metrics/equity/trades.csv + run_card.json),`run_backtest_job` 另打印 `{status,run_id,run_dir,metrics}` JSON。

## 三、方案对比

| 方案 | ① 安全面 | ② 资源 | ③ 部署契合 | ④ artifacts 回传 | ⑤ 复杂度 |
|---|---|---|---|---|---|
| **甲** worker 挂 docker.sock + `docker run` 一次性 | 🔴🔴🔴 **docker.sock = 宿主 root** · worker 跑大量三方库(akshare/ccxt/langgraph)+ 将来 vibe 生成码,被攻破=整机沦陷 | 一次性容器,冷启 ~几秒,跑完释放(省常驻内存) | 需改 worker Dockerfile(装 docker CLI)+ compose 挂 sock | 共享卷 | 中 |
| **乙** vibe 常驻 + worker `docker exec` | 🔴🔴🔴 **docker exec 同样要 worker 能访问 docker.sock** = 宿主 root | 常驻 ~400-700M | 同甲改 worker + 加常驻服务 | 共享卷 | 中 |
| **丙** vibe 常驻 + 自写小 HTTP + worker HTTP 调 | ✅ 无 docker.sock · midas-net 内网隔离 · vibe 是普通无特权服务 | 常驻 ~400-700M(FastAPI+vibe 库)· 冷启省(库预载) | 加常驻服务到 compose · update.sh `up -d` apply | HTTP resp 回 metrics + 共享卷回 equity/trades | 中-高(要写+维护小 HTTP 服务) |
| **丁** 共享卷 + 任务文件 + vibe 轮询 | ✅ 无 docker.sock · 纯文件 IPC | 常驻 ~400-700M(轮询循环) | 加常驻服务 + 共享卷 | 共享卷(天然) | 中(轮询延迟 + 任务文件"原子认领"防重跑要自己搓,偏 hacky) |
| **★戊** vibe 容器内跑专用 Celery worker(消费 `backtest` 队列) | ✅✅ **零 docker.sock** · 纯 Redis 消息(broker 已存在)· vibe 只是另一个 Celery worker | 常驻 ~400-700M(`--concurrency=1` 封顶) | 加 1 个 midas-vibe 服务(跑 celery worker -Q backtest)+ 共享卷 · update.sh `up -d` apply | 共享卷(equity/trades)+ Celery result backend(已配)回 metrics 摘要 | 中(复用现成 Celery/Redis · 无新 IPC 机制) |
| 戊1 `docker compose run` 一次性 | 🔴 仍要 worker 能访问 docker.sock(从 worker 发 compose run)| 一次性 | 同甲 | 共享卷 | 中 |
| 戊2 worker 进程内跑 vibe | ❌ 违背"api/worker 不装 vibe"解耦原则 + worker 是 3.11 / vibe 要 3.12 | — | — | — | — |

## 四、推荐方案 + 理由 + 排除项

### ★ 推荐:戊(midas-vibe 内跑专用 Celery worker · 消费 `backtest` 队列)
**理由**:
1. **零 docker.sock**(根本不碰宿主特权)—— 直接绕开最大安全红线。
2. **复用现成资产**:Redis 已是 Celery broker + result backend,Celery 已是全栈任务系统 —— "worker 触发 vibe"退化成"主 worker 把 backtest 任务 enqueue 到 `backtest` 队列,vibe-worker 消费",**无需新造 HTTP/轮询/exec 任何 IPC**,最 idiomatic。
3. **解耦原则仍守**:主 api/worker 保持**零 vibe**;只有这个**专用 vibe-celery-worker**(=midas-vibe 容器)装 vibe。
4. **职责干净分两段(推荐 戊-a)**:vibe-worker 只**算**(跑 `run_backtest_job` → artifacts 写共享卷 + metrics 经 Celery result 回);**主 worker 落库**(它有 `app.*` + DB 配置,跑 `parse_artifacts` + `persist_result/error`)。→ vibe 容器不需要 DB 凭证、不需要 `app.*` 全家桶,只要 vibe + job + loader + celery。
5. **artifacts 回传**:共享命名卷(如 `midas-backtest-runs` 挂到 midas-worker + midas-vibe 同路径 `/work/runs`)承载 equity/trades.csv(给将来 B 档报告 UI);metrics 摘要走 Celery result。盘 ~21G,artifacts 每跑 KB-MB 级,绰绰有余。

**runner-up:丙(HTTP)** —— 若你更喜欢请求/响应直观、不想引第二个 Celery worker,丙 也安全可行;代价是要写+维护一个小 HTTP 服务(比复用 Celery 多一层造轮子)。

### 排除项(触红线)
- **甲 / 乙 / 戊1 一律排除** —— 都需要给 worker(或其代理)**docker.sock 访问 = 宿主 root 权限**。worker 跑大量三方库且将来要跑 vibe 生成代码,给它宿主 root 是不可接受的攻击面。**除非有强隔离论证,默认排除**(本侦察认为无不可替代性 —— 戊/丙 完全能替代且更安全)。
- **戊2 排除** —— 违背 api/worker 不装 vibe 的解耦原则 + python 版本不一致。

### 资源现实结论
- 任何"worker 不挂 sock 的按需触发"**都必须有一个常驻 vibe 消费者**(worker 没法凭空 spawn 容器)→ 常驻内存 ~400-700M 是**无法避免**的必要成本(不是"非必要的大常驻")。建议给 midas-vibe 限 `memory: 768M` + `--concurrency=1`,留足 ~1.7-2G 余量。

## 五、声明 vs 实测(诚实标注)
1. **未实跑/未建任何东西**:本步只读 compose + Dockerfile + task。所有方案是**纸面架构对比**,P1-4b 实做时以真机为准。
2. **常驻内存 ~400-700M 是估算**(vibe 库 pandas/numpy/+ 可能 langgraph/litellm import 即占):**真值要 P1-4b 建好 midas-vibe-worker 后 `docker stats` 实测**。若超 768M 限额要调。
3. **midas-vibe 镜像当前不含 celery**(P1-4a 只装 vibe + clickhouse-connect):戊 需在 midas-vibe 镜像加 `celery` + worker 入口 + 把 `run_backtest_job` 包成一个 Celery task;丙 需加一个 HTTP 框架。两者都是 P1-4b 要补的镜像/代码改动。
4. **vibe 自带 `api_server`/`mcp_server`**(egg-info top_level 有)——理论上"丙"可复用 vibe 自带 server,但**未核其是否需 LLM/暴露面是否可控**;更稳是自写极小 wrapper 只调 `run_backtest_job`(本报告按此假设)。
5. **共享卷路径/权限**:vibe 容器非 root(uid 10001),主 worker 用户另算 —— 共享卷读写权限对齐要 P1-4b 实配(uid/gid 或卷权限),纸面没验。
6. **update.sh 需补规则**:加 midas-vibe 服务后,`deploy/vibe/` 改动触发镜像重建的规则当前不存在 → P1-4b 要扩 update.sh(否则改了 job/Dockerfile 部署不会重建 vibe 镜像)。
7. **服务器余量(内存 ~2.5G / 盘 ~21G)= 你给的口径**,我没在服务器实测;常驻 +768M 后余量需真机确认不挤爆(CH 已吃 2G)。

---
**一句话**:推荐 **戊(midas-vibe 跑专用 Celery worker 消费 backtest 队列 + 共享卷回 artifacts)**,复用现成 Redis/Celery、零 docker.sock、解耦不破;排除一切要 worker 挂 docker.sock 的方案(甲/乙/戊1)。P1-4b 落地清单见上方"声明 vs 实测"。
