# syntax=docker/dockerfile:1.7
# ────────────────────────────────────────────────────────────────────────────
# midas-xshot · X 营销每日推文截图底座(阶段4a · PR-4)
#
# 只提供 Playwright + Chromium 的截图运行环境(消费 xshot 队列 → 截 crypto-preview 主图卡)。
# ★ 照搬 deploy/vibe 范式:独立镜像(手工 build · 不进 compose build)· 不 import app.* / 不连 DB
#   —— shooter 只截图写 /shots/<id>.png,image_path 落库由【主 worker】link 回调做(解耦)。
# ★ 截公开页(不需 Pro 登录 · 阶段1 验证)· 1.5g mem_limit 硬限(compose 里)· 串行 concurrency=1。
#
# ★★ 镜像【手工 build】(同 midas-vibe,不进 update.sh 的 compose build):
#     docker build -t midas-xshot:0.1.0 deploy/xshot/
#   合并 PR-4 前必须先在 VPS build 成功(否则 compose up 找不到镜像 → 回滚,踩 vibe S1a 坑)。
# ────────────────────────────────────────────────────────────────────────────
# playwright/python 官方镜像:自带 Python + Chromium + 浏览器系统依赖(版本与镜像 tag 对齐,
# ★ 不要再 pip install playwright(会与镜像内置 chromium 版本错配))。
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# ★ 中文字体(阶段1 头号坑:不装则 K线/标注中文全是豆腐□)· fonts-noto-cjk 覆盖简繁。
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 阿里云 PyPI 镜像(HK→大陆线路防 pip 超时,踩过的坑)· extra 兜底 pypi.org。
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_EXTRA_INDEX_URL=https://pypi.org/simple/ \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# celery + redis + ★playwright(同一行 pip · 同一 Python 环境 · 见根因):
# ★★根因(0.1.0 翻车):mcr 镜像自带的 playwright 装在【镜像自身的某个 Python 环境】,但本 Dockerfile
#   `pip install celery` 把 celery 落到另一个 site-packages(/usr/local/lib/python3.10)· celery worker
#   进程跑的 python 只看得到 celery、看不到 playwright → 运行时 `import playwright` → ModuleNotFoundError。
# ★修法:用同一个 `python3 -m pip` 把 playwright + celery + redis 一次装齐 → 三者保证落同一 site-packages
#   → celery 跑的 python 必能 import playwright。compose command 也改 `python3 -m celery`(用同一 python3)。
# ★playwright==1.49.0 钉死 = 基础镜像 tag(v1.49.0)→ 与镜像预装的 /ms-playwright chromium 二进制版本对齐;
#   pip 只装 python 包不下浏览器,浏览器走 PLAYWRIGHT_BROWSERS_PATH(基础镜像已置 /ms-playwright)。
# ★ 不加 app.* / 不加 DB 驱动 / 不塞 DB 凭证 —— shooter 只截图,不落库(解耦)。
RUN python3 -m pip install --no-cache-dir \
    "playwright==1.49.0" "celery>=5.3" "redis>=5.0"

# ★★build-time 守卫(0.1.0 没验直接出镜像翻车的教训 · 最强证明 = build 时真跑一遍 capture.py 的核心动作):
#   ① celery 跑的 python3 能 import playwright(修复直击的 ModuleNotFoundError)
#   ② chromium 二进制真实存在  ③ chromium 真能 --no-sandbox 启动(= 运行时实际操作)
#   任一不过 → build 失败,绝不再出"能 build 但跑起来不行"的带病镜像(0.1.0 教训:没验就出镜像)。
RUN python3 - <<'PY'
import os
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    exe = p.chromium.executable_path
    assert os.path.exists(exe), f"chromium 二进制缺失:{exe}"
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    ver = browser.version
    browser.close()
print(f"[build-check] ✓ playwright import OK · chromium 启动 OK · version={ver} · exe={exe}")
PY

# /shots = 共享卷挂载点(shooter 写 / 主 worker 删 / api 读)· /work = 运行时挂载脚本。
RUN mkdir -p /shots /work
WORKDIR /work

# ★ root 运行(内部容器 · 不暴露端口)· Chromium 在容器内须 --no-sandbox(见 capture.py)。
# 默认 idle 保活;compose command 覆盖为:python3 -m celery -A xshot_celery_app worker -Q xshot。
CMD ["sleep", "infinity"]
