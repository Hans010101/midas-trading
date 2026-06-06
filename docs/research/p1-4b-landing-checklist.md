# P1-4b 落地清单 + 草图(方案戊:midas-vibe 专用 Celery worker)· 2026-06-05

> 只产出**落地设计清单 + 关键代码/compose/Dockerfile 片段草图**供 Hans 审。
> ★ 全部是**草图**(非最终实现)· 不改 compose 生产配置 · 不部署 · 不碰 main。

架构(已定·戊):主 worker 落 pending + `send_task` 到 `backtest` 队列 → midas-vibe 容器内
专用 vibe-worker 消费 → 跑 run_backtest_job 逻辑 → artifacts 写共享卷 → 结果经 Celery 回主
worker → 主 worker `persist_result/error` 落库。**vibe 容器不装 app.*、不拿 DB 凭证(只算不落库)。**

---

## 1. 队列路由隔离(最关键)

**现状**:`celery_config.py` 无 `task_routes`/`task_queues`(全默认队列 `celery`);主 worker 命令
`celery -A celery_app worker --beat --concurrency=2`(**无 `-Q`** → 只消费默认队列 `celery`)。

**设计**:
- 主 worker:**保持无 `-Q`** → 只吃 `celery` 队列 → **绝不会拉到 `backtest` 任务**(Celery 行为:
  无 `-Q` 的 worker 只消费 `task_default_queue`,即使声明了其它队列也不消费)。命令**不变**。
- vibe-worker:`celery -A vibe_celery_app worker -Q backtest --concurrency=1`(**只**消费 backtest)。
- 两者**共用同一 Redis broker**(db1)+ result backend(db2)。

**草图 · `apps/worker/config/celery_config.py` 增加**:
```python
# 主 worker 默认队列(显式化当前隐式默认)
task_default_queue = "celery"
# vibe 任务路由到 backtest 队列(主 worker 无 -Q,不消费 backtest → 不会 import vibe 而崩)
task_routes = {
    "vibe.run_backtest_job": {"queue": "backtest"},
}
```

**★ 隔离铁律**:主 worker 启动命令**永远不要**加 `-Q backtest`(否则它会拉 vibe 任务 → import
vibe 失败崩)。vibe-worker 启动命令**只** `-Q backtest`。

---

## 2. midas-vibe 镜像改动

**Dockerfile 加**(草图 · 在 P1-4a 的 `RUN pip install` 行追加 `celery` + `redis` python 客户端):
```dockerfile
RUN pip install --no-cache-dir \
    "vibe-trading-ai==0.1.9" \
    "clickhouse-connect>=0.8.0" \
    "celery>=5.3" \
    "redis>=5.0"          # celery 的 redis broker/result 传输 · 仅此,不加 app.*/DB 驱动
```
- **不加** `psycopg`/SQLAlchemy/`app.*`(vibe-worker 不落库 → 不需要 DB)。
- **增重估**:celery + kombu + redis(py)≈ **10-25MB**(纯 Python 包,无 C 扩展大头)· 相对 vibe 本体可忽略。

**vibe-worker 的 Celery app(独立最小 · 放 `deploy/vibe/vibe_celery_app.py`)草图**:
```python
"""仅 vibe 容器内跑 · 独立最小 Celery app · 只注册 backtest 任务 · 不 import app.*/不连 DB。"""
import os
from celery import Celery

app = Celery(
    "midas-vibe",
    broker=os.environ["CELERY_BROKER_URL"],       # redis://redis:6379/1(同主 worker)
    backend=os.environ["CELERY_RESULT_BACKEND"],  # redis://redis:6379/2
)
app.conf.task_default_queue = "backtest"

@app.task(name="vibe.run_backtest_job")            # ★ 名字必须与主 worker send_task 一致
def run_backtest_job_task(config: dict) -> dict:
    # 复用 deploy/vibe/run_backtest_job.py 的核心(需重构出纯函数 run_one,见下)
    from run_backtest_job import run_one
    return run_one(config)                          # 永远返回 {status:ok|error, run_id, run_dir, metrics?/error?}
```

**run_backtest_job.py 需小重构**(草图):把现在 `main()` 里的核心抽成 `run_one(config: dict) -> dict`
(不 `sys.argv`、不 `SystemExit`、try/except 包成返回 dict);`main()` 改为 `_load_config(argv)` →
`run_one(cfg)` → print JSON → 退出码。这样 **CLI(P1-4a 验过的跑法)和 Celery task 共用同一核心**。

---

## 3. 共享卷

**compose 加命名卷** `backtest_runs`,挂进 vibe-worker(写)+ 主 worker(读)同路径 `/work/runs`:
- vibe-worker:`backtest_runs:/work/runs`(写 `/work/runs/<run_id>/artifacts/*`)
- 主 worker:`backtest_runs:/work/runs`(读 + 落库后清理)

**权限**(已核):vibe 写侧 = `USER vibe`(uid 10001);主 worker = **跑 root**(其 Dockerfile 无 USER)
→ **root 能读 10001 写的任何文件**,读方向天然通,无需特殊对齐。清理(rmtree)由 root 做也 OK。
> 反方向(若将来主 worker 改非 root)才需共享 gid;当前不需要。**P1-4b 仍建议 docker stats/ls -l 真机核一次**。

**artifacts 清理策略**(盘紧 · 建议):**落库成功后主 worker 立即 `shutil.rmtree(run_dir)`**
(16 指标已进 PG `metrics_json`)。若将来 B 档报告 UI 要 equity/trades 曲线 → 二选一:
(i) 把 equity/trades 也存进 PG(扩 `persist_result` + 加 JSONB 列)然后删卷;
(ii) 保留 run_dir + 加一个 beat 任务定期清 N 天前的目录。**当前推荐 (i) 思路或落库即删,卷只做中转。**

---

## 4. compose 服务片段草图

**`docker/docker-compose.yaml` 加(草图)**:
```yaml
  vibe-worker:
    image: midas-vibe:0.1.9            # 独立镜像(非 compose build)· update.sh 单独 docker build
    container_name: midas-vibe-worker
    restart: unless-stopped
    command:
      - celery
      - -A
      - vibe_celery_app
      - worker
      - -Q
      - backtest
      - --concurrency=1               # ★ 内存现实:封顶一次一个回测
      - --loglevel=info
    environment:                       # ★ 不用 env_file ../.env(避免把 DB/SECRET 全塞进 vibe)
      CLICKHOUSE_HOST: clickhouse
      CLICKHOUSE_PORT: "8123"
      CLICKHOUSE_USER: ${CLICKHOUSE_USER}        # 0014:用无默认 ${VAR}(非 :-fallback)从 .env 取
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}
      CLICKHOUSE_DATABASE: ${CLICKHOUSE_DATABASE:-default}
      CELERY_BROKER_URL: redis://redis:6379/1
      CELERY_RESULT_BACKEND: redis://redis:6379/2
      PYTHONUNBUFFERED: "1"
    depends_on:
      redis: { condition: service_healthy }
      clickhouse: { condition: service_healthy }
    networks: [midas-net]
    volumes:
      - backtest_runs:/work/runs                                              # 共享 artifacts
      - ../apps/api/app/services/backtest/midas_ch_loader.py:/work/midas_ch_loader.py:ro  # loader 单一来源挂载
      - ./vibe/run_backtest_job.py:/work/run_backtest_job.py:ro
      - ./vibe/vibe_celery_app.py:/work/vibe_celery_app.py:ro
    # 不映射任何端口(不经 Caddy / 不面向公网)· 镜像已 USER vibe(非 root)
```
```yaml
volumes:
  backtest_runs:
    name: midas-backtest-runs
```

**`docker/docker-compose.prod.yaml` 加(草图)**:
```yaml
  vibe-worker:
    restart: always
    deploy:
      resources:
        limits:
          memory: 768M        # ★ 初值 · P1-4b 建好必 docker stats 实测调(余 ~2.5G,CH 已吃 2G)
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "5" }
```

**loader 进容器方式**:**运行时挂载**(上面 `:ro`)—— 倾向挂载而非 COPY,因为 loader 随 apps/api
单一来源走,**改 loader 不用重建 vibe 镜像**(只重起 vibe-worker 重新 import)。

---

## 5. 主 worker 侧改动(块3 task 的 TODO 接上)

**草图 · `apps/worker/tasks/backtest.py`**(主 worker 有 app.*,但**不 import vibe**,用 `send_task` by name):
```python
from celery import current_app, shared_task, signature

@shared_task(bind=True, name="tasks.backtest.run_backtest", max_retries=0)
def run_backtest(self, params, user_id=None):
    bt_params = BacktestParams(**params)
    config = build_backtest_config(bt_params)          # 早校验 period
    run_pk = asyncio.run(_create_pending(bt_params, UUID(user_id) if user_id else None))
    # 共享卷路径(vibe + worker 同挂 /work/runs)
    config["run_id"] = str(run_pk)
    config["run_dir"] = f"/work/runs/{run_pk}"
    # enqueue 到 backtest 队列(by name · 不 import vibe)· 成功回调 persist_outcome
    current_app.send_task(
        "vibe.run_backtest_job",
        args=[config],
        queue="backtest",
        link=signature(
            "tasks.backtest.persist_outcome",
            args=[run_pk],
            queue="celery",          # ★★ 必须显式 pin celery 队列(否则被 vibe app 路由进 backtest → 主worker收不到)
        ),
    )
    return {"backtest_run_id": run_pk, "status": "pending"}

@shared_task(name="tasks.backtest.persist_outcome", max_retries=0)
def persist_outcome(vibe_result, run_pk):
    asyncio.run(_persist(vibe_result, run_pk))

async def _persist(vibe_result, run_pk):
    engine = create_async_engine(settings.database_url); maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            run = await session.get(BacktestRun, run_pk)
            if vibe_result.get("status") == "ok":
                params = BacktestParams(**run.params_json)             # 从 pending 行重建
                result = parse_artifacts(Path(vibe_result["run_dir"]), params)
                await persist_result(session, run, result, run_id=vibe_result.get("run_id"))
            else:
                await persist_error(session, run, vibe_result.get("error", "unknown"), run_id=vibe_result.get("run_id"))
            await session.commit()
    finally:
        await engine.dispose()
    shutil.rmtree(vibe_result.get("run_dir", ""), ignore_errors=True)   # 落库后清卷(防堆积)
```
- **非阻塞**:`run_backtest` enqueue 后立即返回(不 `.get()` 占主 worker slot)。vibe 跑完 → Celery 触发
  `persist_outcome`(回 celery 队列 → 主 worker)→ 落库 + 清卷。
- **简化备选**(低 QPS 可选):`send_task(...).get(timeout=...)` 阻塞拿结果再落库 —— 逻辑更简单但
  **占一个主 worker slot 整个回测时长**(concurrency=2 → 2 个并发回测堵死);研究低频可接受,但默认推非阻塞 link。

---

## 6. update.sh 补规则(草图)

现状:update.sh diff 只认 apps/api·apps/worker·apps/web·docker/*.yaml;**无 deploy/vibe 规则**
→ 改了 vibe 镜像源**不会自动重建**(三方解耦隐患)。补:
```bash
# deploy/vibe/(镜像源:Dockerfile/job/celery_app)改了 → 重建 midas-vibe 镜像 + 重起 vibe-worker
if echo "$CHANGED" | grep -qE "^deploy/vibe/(Dockerfile|.*\.py)$"; then
    echo "  ▸ 检测到 deploy/vibe/ 改动 → docker build midas-vibe:0.1.9 + 重起 vibe-worker"
    docker build -t midas-vibe:0.1.9 deploy/vibe
    $COMPOSE up -d vibe-worker
fi
# loader 是运行时挂载:apps/api/.../midas_ch_loader.py 改了(已触发 api+worker 重建)→
#   顺带重起 vibe-worker 让它重新 import 挂载的 loader(无需重建镜像)
if echo "$CHANGED" | grep -qE "^apps/api/app/services/backtest/midas_ch_loader\.py$"; then
    echo "  ▸ loader 改动 → 重起 vibe-worker(重载挂载的 loader · 不重建镜像)"
    $COMPOSE up -d --no-deps vibe-worker
fi
```
> ★ midas-vibe 是 `image:`(非 compose `build:`)→ 必须 update.sh 手动 `docker build`(compose up 不会建它)。

---

## 最小验证路径(P1-4b 实现后 · feature 分支隔离 · 不碰生产)

1. 本地/staging:`docker build -t midas-vibe:0.1.9 deploy/vibe`(含 celery)。
2. 起栈(dev compose 或隔离环境):redis + clickhouse + 主 worker + vibe-worker + 共享卷。
3. **enqueue 一次**:`celery -A celery_app call tasks.backtest.run_backtest --args='[{"symbol":"BTCUSDT","start":"2025-01-17","end":"2026-05-31"}]'`(或写个 5 行脚本调 `.delay()`)。
4. **验端到端**:
   - PG `backtest_runs` 先出 `pending` 行;
   - **vibe-worker 日志**消费 `vibe.run_backtest_job`(主 worker 日志**不**出现该任务名 = 路由隔离成立);
   - 共享卷 `/work/runs/<id>/artifacts/` 出 metrics/equity/trades.csv;
   - `persist_outcome` 在主 worker 跑 → PG 行变 `done` + `metrics_json` 16 指标;run_dir 被清。
   - vibe-worker 日志确认 `LOADER_REGISTRY size=0`(红线:只走 MidasCHLoader)。
5. 失败路径:喂个查无数据的 symbol → vibe 返回 status=error → PG 行 `error` + error 文本。

---

## 风险 / 未知点 + 声明 vs 实测(★ 三处重点)

1. **★ 内存(未实测)**:vibe-worker 常驻 RSS 估 ~400-700M(vibe 库 import 即占),**真值要 P1-4b
   建好 `docker stats` 实测**。768M 限额是初值;若 vibe 在 task import 时拉起 langgraph/litellm 可能更高 →
   超了要调限额 / 确认 2.5G 余量(CH 已吃 2G)不被挤爆 OOM。
2. **★ 队列路由(纸面·需实证)**:"主 worker 无 -Q 不消费 backtest" 是 Celery 默认行为推断 →
   **P1-4b 必看主 worker 日志确认从不出现 `vibe.run_backtest_job`**(误配会让主 worker 拉它 → import vibe 崩)。
   缓解:显式 `task_default_queue="celery"` + `task_routes` + 主 worker 永不加 `-Q backtest`。
3. **★ 卷权限(单向已核·反向未核)**:worker 跑 root → 读 vibe(10001)写的文件 OK(已确认无 USER)。
   但 **P1-4b 仍真机 `ls -l` 核一次**;若日后主 worker 改非 root,需共享 gid / world-readable。
4. **link 跨 app 路由陷阱(重点)**:vibe-worker 用 vibe app 触发 link 回调,**必须给 link signature
   显式 `queue="celery"`**,否则被 vibe app 的 `task_default_queue=backtest` 路由进 backtest 队列 →
   vibe-worker 自己收(它没 app./没 persist 任务)→ 落库永不发生。草图已 pin,P1-4b 务必保留。
5. **send_task by name**:主 worker enqueue `"vibe.run_backtest_job"` 不在本地定义(broker 级)→
   名字与 vibe app `@app.task(name=...)` **必须逐字一致**,否则任务卡队列无人消费。
6. **vibe 自带 api_server/mcp_server 未用**:本方案自建最小 celery app,不碰 vibe 自带 server(避免引入 LLM/多余暴露面)。
7. **共享卷 run_dir 路径契约**:主 worker 写 `config["run_dir"]="/work/runs/<run_pk>"`,vibe job 必须用
   config 里的 run_dir(P1-4a 的 job 已支持 `cfg.get("run_dir")`)→ 两边路径一致才读得到。
8. **未写任何最终实现**:以上全是草图;P1-4b 实做以真机为准。

---
**一句话**:6 项落地点 + 草图齐备,核心是「队列路由隔离(主无-Q / vibe -Q backtest)+ link 显式 pin
celery 队列 + 共享卷中转 artifacts + vibe 镜像加 celery 不加 app.* + update.sh 补 vibe 重建规则」。
三处必须真机实证:**内存 / 队列隔离 / 卷权限**。等你回来审 + 拍 P1-4b 开做。
