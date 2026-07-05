# 0044 · Celery worker 慢性 OOM · 子进程回收治理

- 状态:Accepted
- 日期:2026-07-05
- 相关:apps/worker/config/celery_config.py · docker-compose.prod.yaml worker

## 背景(症状)

主 Celery worker 近日被 cgroup OOM killer 周期性杀:dmesg 显示近日 4 次(7/2 一天 3 次)。
表现是【慢性】——不是某次单任务爆内存突刺,而是运行数日后内存单调爬升,最终触顶被杀。

## 诊断(根因)

**根因 = `--concurrency=4` 的 4 个 fork 子进程【永不回收】,叠加高频任务长时运行内存单调爬升,
数日后突破 2G cgroup 硬顶。**

证据链(纯代码/配置分析 · VPS dmesg 由 Hans 侧观察佐证):

1. **worker 命令无任何子进程回收配置**:`celery -A celery_app worker --beat --concurrency=4`
   (apps/worker/Dockerfile / docker-compose.prod.yaml)· celery 默认 `worker_max_tasks_per_child=None`
   + `worker_max_memory_per_child=None` → 4 个 prefork 子进程从启动到部署重建期间【从不重启】。

2. **cgroup 硬顶 2G**:docker-compose.prod.yaml worker `deploy.resources.limits.memory: 2G`。
   注释记录稳态估算 `4 × ~365M ≈ 1.46G < 2G`——**稳态本安全**,问题不在稳态峰值。

3. **高频任务提供「爬升燃料」**:beat 里 5 个【每分钟】任务(scan_price_anomalies /
   scan_alert_rules / perp scan_liquidations / conditional scan_triggers / perp cross)
   ≈ 每子进程 ~1800–7200 次/天,外加 5min/10min/30min 采集/flush。任一任务留下的
   Python 分配器碎片 / 三方库(pandas/httpx/sqlalchemy 连接)缓存 / 偶发未即时释放的对象,
   在【永不重启】的子进程里【只增不减】→ RSS 单调爬升 → 数日破 2G → cgroup OOM。

结论:这是「无回收 → 单调爬升」的经典 celery 长跑内存病,不是某个任务的 bug。
（若要精确归因到哪个任务,需 VPS 侧按子进程 PID 抓 RSS 时序;但治理不依赖精确归因——
 回收机制对任意来源的累积内存都有效。)

## 决策(修法 · 纯配置 · celery 标准 OOM 解法 · 零任务逻辑改动)

celery_config.py(module-level · `config_from_object` 自动生效)加两条:

```python
worker_max_tasks_per_child = 200      # 每子进程跑 200 任务后优雅重启(周期兜底 · 释放全部累积内存)
worker_max_memory_per_child = 450_000 # KB(≈440MB)· 常驻内存超阈 → 当前任务完成后即换新子进程
```

- **max_memory_per_child = 440MB**:精准封顶。健康子进程稳态 ~365M【不触发】(只回收异常膨胀的);
  一旦某子进程 RSS 超 440M(累积/泄漏),它做完当前任务即被替换 → 4 × 440M ≈ 1.76G < 2G 硬顶,
  留 ~240M 余量。直接消除「爬升破顶」的可能。
- **max_tasks_per_child = 200**:周期性兜底,即便内存没超阈也每 200 任务换一次新子进程
  (高频任务下每子进程约 50–100 分钟一轮 · fork 开销可忽略)。
- 两者是「阈值触发 + 周期兜底」双保险。★优雅重启:celery 在【当前任务完成后】才换子进程,
  绝不中断执行中的任务(不丢任务 · 不影响撮合/推送等)。

## 影响面 / 回归

- 纯配置项 · 不改任何 task 逻辑 · 不碰 broker/schedule/队列路由。
- 唯一行为变化:子进程会周期性/超阈重启(标准 celery 运维手段)· 无状态 worker 任务
  不受影响(每任务自建 engine/redis 连接 · 见 visit_flush / ai_reflection 范式)。
- vibe-worker(-Q backtest · concurrency=1 · 独立容器 256M)不受此配置影响(它 config 相同但
  concurrency=1 + 内存足 · 加回收更保险无害)。

## 验证

- 部署后观察:worker RSS 不再单调爬升(达 ~440M 即回落)· dmesg 不再出现 worker OOM-kill。
- ★这是【运行数日才显现】的治理,真机确认需 Hans 观察 3–7 天 dmesg / `docker stats midas-worker`。
