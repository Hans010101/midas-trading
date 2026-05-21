# 0015 · Worker OOM · Celery concurrency × 重库内存 vs 单 VPS 限额(2026-05-21 部署翻车 #3)

## 状态
Recorded (2026-05-21)

## 事故

部署 STEP 10 修了 0013 (ports merge) + 0014 (DATABASE_URL 插值)
后,docker compose ps 显示 5 服务 healthy · 但 worker 反复 restart:

```
docker inspect midas-worker
  State.Status      = restarting
  State.ExitCode    = 137         ← OOM
  State.RestartCount = 15
```

`137 = 128 + 9` = SIGKILL · Docker OOMKiller 砍了进程。

STEP 12 数据预热(`docker exec midas-worker python -m tasks.data_ingest`)
没法跑 · 因为容器在 restart 状态 · `docker exec` 失败。
ClickHouse `kline` 表 0 行。

## 根因

worker `apps/worker/Dockerfile:25` 默认:
```
CMD ["celery", "-A", "celery_app", "worker", "--beat", "--loglevel=info", "--concurrency=4"]
```

Celery prefork 模型 · `--concurrency=4` 起 1 主进程 + 4 worker 进程 ·
**每个进程都要 import** akshare / ccxt / yfinance / langchain / langgraph /
czsc 这堆数据 + AI 重库。

Python import-time 内存:每进程 ~300 MB resident。
- 主 + 4 workers ≈ 5 × 300 = **1.5 GB**

`docker-compose.prod.yaml` worker 限额 **512 MB** · cgroup 限制下 ·
内存涨过 512M 立刻 OOMKill · 触发 docker restart-always · 循环 15 次。

为什么之前没踩(M0/dev)?
- dev 没设 memory limit · 全机 8GB 随便用
- M0 验收用本机 docker · 同样不限

生产模式 `docker-compose.prod.yaml` 第一次上 cgroup 限额 · concurrency
仍是 4 · 数学上就不可能跑。**写 prod 限额时漏算了 Python 重库 ×
prefork 进程的乘积。**

## 决策

### 1. concurrency 4 → 2

M1 流量预期(虚拟交易 + 数据预热 + 价格异动检测 + AI 缓存预算):
- 高频:每分钟价格异动扫描 1 次
- 中频:每日成交快照、回填增量
- 低频:用户触发的 AI 决策卡(已有 LiteLLM 缓存层)

**concurrency=2 完全够用 ·** prefork=2 时:
- 1 主 + 2 workers = 3 × 300M ≈ 900M

### 2. memory limit 512M → 1G

留 100M 缓冲给 GC + cgroup 计量误差。

### 3. 整机 8G 重新平衡

| 服务 | 旧 | 新 |
|---|---|---|
| postgres | 768M | 768M |
| clickhouse | 2G | 2G |
| redis | 256M | 256M |
| api | 1G | 1G |
| **worker** | **512M** | **1G** |
| web | 768M | 768M |
| **小计** | 5.3G | **5.8G** |
| OS + 缓冲 | 2.7G | **2.2G** |

仍留 2.2G 给 OS + Docker daemon + 突发 + 数据预热子进程,健康。

### 4. 不动 Dockerfile · 用 compose command 覆盖

`apps/worker/Dockerfile` CMD 留 `--concurrency=4`(本机 dev 跑 docker
全速利用)· 生产用 compose `command:` 字段覆盖成 `--concurrency=2`。
这样 dev / CI / prod 三套需求都满足:
- dev `docker compose up`(无 prod overlay):用 Dockerfile 默认 4
- prod `docker compose -f base -f prod up`:用 prod overlay 的 2

## 教训

1. **资源限额 + 多进程乘数效应**:任何 cgroup memory limit 时,
   必须算清楚「单进程内存 × 进程数」是否落在 limit 内。
   prefork worker、gunicorn workers、nginx workers 都同此理。
2. **Exit code 137 = OOMKill** · 不是网络错、不是配置错。restart
   loop + RestartCount 单调上涨是典型征兆。
3. **Python ML/数据栈很重** · 不要拿 Flask hello-world 的内存直觉
   去估 akshare/ccxt/langchain 这种栈。每进程基础 250-350M。
4. **生产首次上限额时跑一次 docker stats** · 看实际 RES 内存 ·
   再决定 limit。事前估计常常低 30-50%。
5. **dev vs prod 启动参数差异** 用 compose command 覆盖,不要
   改 Dockerfile 默认值 · 保持镜像一份多用。

## 防御性补丁(M2 可加)

- compose prod overlay 加 healthcheck 跑「celery -A celery_app inspect ping」
  · worker OOM 重启时 healthcheck 立即转 unhealthy · 直接被 docker compose
  ps 抓出来,不依赖 RestartCount 人工核查。
- 监控:Celery worker memory 长期占用接近 limit 时 alert(M2 接 metrics)。

## 跟 0013/0014 的关系

部署 STEP 10 一共踩三个坑:
- 0013 · compose ports MERGE(没用 !override)→ bind 冲突
- 0014 · YAML 插值 + env_file 覆盖 → DATABASE_URL 用 midas_dev
- 0015 · 此条 · worker 内存 vs concurrency 错配 → OOM 循环

三个都属于「prod 资源 / 配置首次上限,跟 dev 默认值不匹配」类。
教训:写 docker-compose.prod.yaml overlay 时,必须把 base 的每条
默认假设(端口绑 0.0.0.0、内存无限、ports 数组合并、env 来自 shell
环境)逐项重审。
