# syntax=docker/dockerfile:1.7
# ────────────────────────────────────────────────────────────────────────────
# midas-vibe · Vibe 回测运行底座(P1-4a)
#
# 只提供 vibe-trading-ai==0.1.9 + clickhouse-connect 的运行环境。
# ★ 产品 loader(MidasCHLoader)+ harness 不烤进镜像 —— 运行时挂载(随 apps/api 代码
#   单一来源走,镜像保持稳定、不随业务码变;路径B 显式传 loader,无 registry 依赖)。
# ★ 钉死 vibe==0.1.9(升级须复验路径B)· 非 root 运行 · 不设任何 shell 工具开关。
# ★ 只读 CH:loader 全程 SELECT/EXISTS,绝不写(见 apps/api/.../midas_ch_loader.py)。
#
# 本步(P1-4a)只建镜像本体;compose/Celery/服务形态 = 后续 P1-4b。
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# 阿里云 PyPI 镜像(HK→大陆线路防 pip 超时,踩过的坑)· extra 兜底 pypi.org。
# PYTHONDONTWRITEBYTECODE:不写 .pyc(更瘦)· PYTHONUNBUFFERED:日志实时不缓冲。
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_EXTRA_INDEX_URL=https://pypi.org/simple/ \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 钉死 vibe==0.1.9 + clickhouse-connect(HTTP 8123 读 CH · 对齐 apps/api 的 >=0.8.0)。
# P1-4b 加 celery + redis(py 客户端):vibe-worker 消费 backtest 队列。
# ★ 不加 app.* / 不加 DB 驱动(psycopg/SQLAlchemy)/ 不塞 DB 凭证 —— vibe-worker 只算不落库(解耦)。
# --no-cache-dir 省镜像体积(盘紧)· 单条 RUN。
# 注:python:3.12-slim 实测 pip 即可装通(P1-3 路径B 在 slim 上退出码0),无需额外 apt。
RUN pip install --no-cache-dir \
    "vibe-trading-ai==0.1.9" \
    "clickhouse-connect>=0.8.0" \
    "celery>=5.3" \
    "redis>=5.0"

# 非 root:vibe(未来)会在容器内跑生成的策略代码,非 root 收敛风险。
# 固定 uid 便于挂载卷权限对齐;/work 为运行时挂载点(loader + harness 放这)。
RUN useradd --create-home --uid 10001 vibe \
    && mkdir -p /work \
    && chown -R vibe:vibe /work
WORKDIR /work
USER vibe

# ★ 不设任何 shell 工具开关环境变量(VIBE_TRADING_ENABLE_SHELL_TOOLS 等一律不设)。

# 本步不定服务形态(P1-4b 才定:Celery worker / 一次性 job)· 默认 idle 保活,
# 供 docker run 覆盖 CMD(python /work/ch_smoke.py)或 docker exec 跑 harness。
CMD ["sleep", "infinity"]
