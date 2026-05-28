# syntax=docker/dockerfile:1.7
# ↑ BuildKit 语法 · 使能 RUN --mount=type=cache(ADR 0029 DP1)
FROM python:3.11-slim

WORKDIR /app

# 系统依赖 + curl(healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 拷源码(避免 setuptools.packages.find 在空目录返回空报错)
COPY . .

# 装运行时 + dev 依赖
# ── ADR 0029 DP1:BuildKit pip cache + 阿里云 PyPI 镜像(extra-index 兜底 pypi.org)──
# · --mount=type=cache · 把 ~/.cache/pip 挂成 BuildKit 缓存层 · 不写入镜像、跨 build 复用 wheel
# · --index-url 阿里云镜像(HK→大陆线路通常优于 HK→pypi.org US CDN);若实测反慢回退见 ADR §7 DP1
# · --extra-index-url 兜底 pypi.org · 防 Aliyun 缺包/版本滞后
# · 移除原 --no-cache-dir(与 BuildKit cache mount 互斥 · 会让缓存挂载空跑)
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -e ".[dev]" \
    --index-url https://mirrors.aliyun.com/pypi/simple/ \
    --extra-index-url https://pypi.org/simple/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=10 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# 生产模式启动:不带 --reload(开发热重载)· 单进程(lifespan 单例:ClickHouse / ccxt / 数据源)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
