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
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=10 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
