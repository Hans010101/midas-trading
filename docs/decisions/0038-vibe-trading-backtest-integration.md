# ADR 0038 · 接入 Vibe-Trading 回测引擎(研究室模块 · 路径 B · 只读 ClickHouse)

- 状态:**Accepted**(可行性 + 真数据 + P1-4 上生产全实测验完;研究室回测后端正式在生产运行,前端 P1-4d 待做)
- 日期:2026-06-05(创建)/ 2026-06-07(P1-4 上生产收官)
- 相关:研究室模块(策略回测 / 多智能体研讨 / 因子量化);P0 地基验证、P1-2 路径 B 冒烟、P1-3 真 CH 喂回测、P1-4 产品化上生产
- 备注:本 ADR 在协作过程中曾临时称「0032」,但 docs/decisions/0032 已被「多通道 Bot 架构 + 飞书接入」占用,故正式归档为 0038(decisions 目录下一空号)。

## 背景与目标

把开源 HKUDS/Vibe-Trading 回测引擎(与 LightRAG 同实验室出品,MIT 许可,Python/FastAPI,
默认 DeepSeek,明确不接真实交易)作为「点金 Midas」的独立「研究室」模块接入,经容器隔离
提供策略回测能力。核心板块:策略回测(首期重点)、多智能体研讨(后续)、因子量化(转未来)。

砍掉的形态:智能客服(重型量化 agent 误配);真实券商对账单复盘 + 解析(短期需求有限、隐私面
+ 解析维护包袱,未来若做走「虚拟交易复盘」复用虚拟引擎逐笔记录)。

红线:回测纯研究,全程虚拟、绝不接真实交易、绝不连 place_market_order / 虚拟下单引擎;
只读 ClickHouse、绝不写;不另开采集旁路。

## 关键决策

### D1 · 路径 B(显式传 loader),非路径 A(覆盖 registry)
直接 import CryptoEngine + 显式传 MidasCHLoader 调 run_backtest,全程不碰
registry / _get_loader / resolve_loader → 「只读 CH、无外部源 fallback」成为架构事实而非运行时
祈祷。排除路径 A(覆盖 LOADER_REGISTRY,靠私有行为脆弱)。

### D2 · 数据源只读 ClickHouse
写 MidasCHLoader 读 kline 表 perp 数据;OKX/CCXT 退路彻底不用(虽实测香港 VPS 可达)。
loader 实现 vibe DataLoaderProtocol:类属性 name/markets/requires_auth + is_available() + fetch();
符号双向归一(查 CH 用带斜杠 BTC/USDT,喂引擎/写盘用不带斜杠 BTCUSDT,避免引擎把 "/" 当路径分隔符);
interval 大写→Midas period 小写映射;空结果明确 raise 不静默。

### D3 · 触发架构 = 方案戊(vibe 跑专用 Celery worker)
midas-vibe 容器内跑专用 Celery worker 消费 backtest 队列:主 worker enqueue → vibe-worker 消费
跑 run_backtest_job → artifacts 写共享卷 → 结果经 Celery 回 → 主 worker persist 落库。
零 docker.sock(排除「worker 挂 socket = 宿主 root」的甲/乙方案)、复用现成 Redis/Celery、
主 api/worker 不装 vibe(解耦),vibe 容器不装 app./不拿 DB 凭证(只算不落库)。

### D4 · 报告 UI 走 B 档(取数据自渲染)
不嵌 Vibe 的 UI,用 Midas 设计语言自渲染;专业感靠统一出品语言 + Trust Layer 方法学脚注
(run_card.json)+ 结论先行。

## P0 地基验证(全部真机实测通过)
CH 历史深度(kline 表四市场,crypto perp 头部 BTC/USDT 503 根日线)、OKX/CCXT 香港 VPS 可达、
资源余量(清理构建缓存回收 ~13-15G)、Vibe 0.1.9 可装可跑(阿里云 PyPI 镜像防超时)、
artifacts 落 run_dir/artifacts/*.csv(metrics 16 指标 / equity / trades / positions / ohlcv + run_card)。

## P1-3 真 CH 数据喂回测实测结论(2026-06-06)
隔离容器 + 产品级 MidasCHLoader 走路径 B 调 CryptoEngine.run_backtest 读真 BTC/USDT perp 日线:
- loader.is_available()=True(真连生产 CH:clickhouse:8123 HTTP,只读);
- 16 真实指标(total_return -18.5% / sharpe -0.46 / win_rate 17% …,数值自洽);
- 5 artifacts 全落地;LOADER_REGISTRY size=0 + 「data fed ONLY by MidasCHLoader」红线实测焊死。

CH 连接定死:网络 midas-net、host=clickhouse(=midas-clickhouse 同容器)、HTTP port=8123
(native 9000 仅 TCP,clickhouse-connect 不走)、user=midas、db=default、密码取自 /opt/midas/.env。

### 实测暴露并已兜住的数据质量问题
CH 里 BTC perp 日线有重复日期(503 根 > 实际天数 → 引擎 _align reindex 撞 duplicate labels)。
loader 已加去重:frame[~frame.index.duplicated(keep="last")](同日留最后写入)。
采集端为何写重 = 数据质量技术债,另行排查(不只影响回测)。

## P1-4 实施收官记录(2026-06-06 ~ 06-07)
P1-4a~b 已全部实测落地、合 main、正式在生产环境端到端跑通。状态:研究室回测后端正式上生产
(用户暂不可见,P1-4d 前端待做)。

### 实测里程碑
- P1-4a:midas-vibe:0.1.9 镜像建成(1.86GB),产品 loader 真 CH 回测通过。
- P1-4c:后端代码(回测服务层 / vibe 执行入口 run_backtest_job / Celery 骨架 + 落库
  + alembic 迁移 backtest_runs)碰 apps/api 的全 CI 绿。
- P1-4b:架构=戊。侦察→落地清单→编排骨架(b-1)→加固(b-2:超时三层 + 内存 768→256M + 卷清理)。
- 合 main 后正式环境端到端实测(BTCUSDT perp):主 worker enqueue → vibe-worker 消费
  run_backtest_job(1.87s)→ artifacts 写共享卷 → link 回调 persist_outcome → PG 落
  status=done + 16 指标。LOADER_REGISTRY=0 红线守住;路由隔离成立;现有四市场任务零影响。

### 戊架构关键决策(实现必守)
- 主 worker 保持【无 -Q】= 只消费默认 celery 队列、绝不订阅 backtest(没装 vibe,订阅会崩)
  —— 隔离核心,靠「物理不订阅」而非配置技巧。
- link 回调必须显式 queue="celery"(否则被 vibe app 默认队列吞进 backtest,主 worker 收不到 → 不落库)。
- send_task name "vibe.run_backtest_job" 两端逐字一致。
- vibe 镜像不装 app./不拿 DB 凭证(只算不落库,主 worker 落库)。
- vibe-worker 实测常驻内存仅 ~64.5MiB(限额 768M → 256M)。

### 合 main 部署四个排障教训(均 diagnosis-first,无 blind retry)
1. **worker rebuild 才认 task**:worker 代码构建进镜像(非挂载),旧镜像不含 tasks.backtest →
   "unregistered task" KeyError。走正规 push→Actions→update.sh 重建 worker 镜像后自然认得。
   教训:内置镜像的代码改动必须 rebuild,切分支/抓文件不够。
2. **compose 插值找 project-directory 的 .env**:vibe-worker 用 ${CLICKHOUSE_PASSWORD} 插值,
   compose 插值的 .env 查找基准是【第一个 -f 文件所在目录(docker/)】而非 CWD;docker/.env
   不存在 → 插值空 → recreate 失败(update.sh:292)→ deploy.yml 自动回滚。修法:改用
   env_file: ../.env(相对 compose 文件位置解析到仓库根 .env),与现有 6 服务一致。
3. **celery worker 进程 sys.path 不含 /work**:vibe_celery_app.py 裸 import run_backtest_job,
   celery worker sys.path 不保证含 WorkingDir;手动 python 自动加 cwd 故「手动测通、celery 内炸」
   (假通过陷阱)。修法:vibe_celery_app.py 顶层加
   sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))。验证须模拟 celery 加载。
4. **共享卷属主权限**:卷早期 root 上下文创建,属主 root;vibe-worker 非 root(uid 10001)
   写不进 → PermissionError。临时修(M1a)chown 卷;持久修(M1b)vibe-worker user=0:0 起 +
   command 内 chown /work/runs + celery --uid=10001/--gid=10001 原生降权(每次启动 re-chown,
   删卷重建自动修复;主进程降到非 root)。
   验证状态(M1b-Va 取舍):已实测 — celery 主进程 PID1/worker 进程 uid=10001(/proc 读取确认,
   非 root 红线守住)、vibe-worker 重启时 chown 执行(/work/runs 属主 10001、无 PermissionError、
   回测落 done)。未独立实测 — 「全新卷(初始 root 属主)」场景,因该卷被主 worker + vibe-worker
   同时挂载,删卷需停主 worker(动现有四市场后台任务,代价 > 收益);但全新卷与已有卷走同一条
   `chown -R 10001:10001 /work/runs` 启动命令(强制改属主,与初始属主无关),逻辑上必然覆盖,
   故接受为成立。

### 部署纪律印证(ADR 0033 + ADR 0031)
- 三件套(Actions 绿 + 容器真重建[看 update.sh 日志含 vibe 镜像 build] + 真机抽查)全程执行。
- deploy.yml 先 OLD_HEAD=git rev-parse → reset --hard origin/main → 传 OLD/NEW_HEAD 给
  update.sh(对齐 ADR 0031),确保跑新 update.sh + diff 命中 deploy/vibe → vibe 镜像必 build。
- 第一次合 main 因教训 2 失败并自动回滚(生产零损),诊断后修复再合成功 —— 回滚机制是安全网。

## 技术债(记账)
- M1b 已落地(启动 re-chown + 降权),取代 M1a 临时 chown。
- CH kline 采集端重复 perp 日线根因(loader 去重已兜住,治本另排,勿插队 = K2b 决策)。
- DeepSeek 模型名:已查清无写死 v3.2,唯一 deepseek/deepseek-chat(env LLM_MODEL 可覆盖)——无隐患。
- env 最小化降级:vibe-worker 现用 env_file ../.env 全量注入(S1a 取舍);最小权限可作后续优化。
- 待 Vibe 升级时复验路径 B 仍成立。

## 后续
- P1-4d:B 档报告前端(读 metrics/equity/trades + run_card,Midas 设计语言渲染,结论先行
  + Trust Layer 方法学脚注)。研究室从「后端通」走向「用户可见可用」。
