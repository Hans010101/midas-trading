# syntax=docker/dockerfile:1.7
# ↑ BuildKit 语法 · 使能 RUN --mount=type=cache(ADR 0029 DP1)
FROM python:3.11-slim

WORKDIR /repo

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制 api + worker 两个包到镜像
# worker 直接 import app.*(schemas / services / data_sources),避免重复实现
COPY apps/api /repo/apps/api
COPY apps/worker /repo/apps/worker

# ── ADR 0029 DP1:BuildKit pip cache + 阿里云 PyPI 镜像 ──
# 两个 RUN 共享同一份缓存挂载(target 相同 · sharing=locked 串行写入避免竞态)
# 装 api 包(带全部数据源依赖,提供 app.* 模块)
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    cd /repo/apps/api && pip install -e ".[dev]" \
    --index-url https://mirrors.aliyun.com/pypi/simple/ \
    --extra-index-url https://pypi.org/simple/

# 装 worker 包(自身依赖,与 api 重叠的不会重装)
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    cd /repo/apps/worker && pip install -e ".[dev]" \
    --index-url https://mirrors.aliyun.com/pypi/simple/ \
    --extra-index-url https://pypi.org/simple/

WORKDIR /repo/apps/worker

# M0 简化:把 beat 跟 worker 合在一个容器(`--beat`)。
# 注意:--beat 只能有一个实例,M0 单 worker 没问题;
# 生产 horizontal scale 时要把 beat 拆成独立服务。
CMD ["celery", "-A", "celery_app", "worker", "--beat", "--loglevel=info", "--concurrency=4"]
