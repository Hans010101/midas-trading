#!/bin/bash
# 点金 Midas · 数据缺口回填脚本
# 2026-05-21 · 补 STEP 12 限流时漏掉的:BTC/USDT 全周期 + 600519 1h/1w
#
# 用法(服务器):
#   cd /opt/midas
#   git pull
#   bash scripts/backfill-gap-data.sh 2>&1 | tee /tmp/backfill-gap.log
#
# 安全策略:
#   · 整体 set +e · 永远不中止 · 即使全部失败也跑完最终行数统计
#   · 每个标的×周期最多重试 3 次 · 指数退避 5s/15s/30s
#   · 不动其他容器 · 只 docker exec midas-worker

set +e  # 整体允许失败 · 限流是常态 · 不能让一次失败把整个脚本中止
set -u  # 但变量未定义还是要抓

RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; NC=$'\033[0m'

banner() {
  echo ""
  echo "${CYAN}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${CYAN}║  === $1 ===${NC}"
  echo "${CYAN}╚═══════════════════════════════════════════════════════════${NC}"
}
ok()   { echo "${GREEN}  ✓ $1${NC}"; }
warn() { echo "${YELLOW}  ⚠ $1${NC}"; }

if [ ! -d /opt/midas/.git ]; then
  echo "${RED}❌ /opt/midas 不是 git 仓库${NC}"; exit 1
fi
cd /opt/midas

# ============================================================
banner "1/4 · 前置检查 · worker + clickhouse 都 ready"
# ============================================================
WORKER_STATE=$(docker inspect -f '{{.State.Status}}' midas-worker 2>/dev/null || echo "no-container")
CH_HEALTH=$(docker inspect -f '{{.State.Health.Status}}' midas-clickhouse 2>/dev/null || echo "no-container")
echo "  midas-worker     = $WORKER_STATE"
echo "  midas-clickhouse = $CH_HEALTH"

if [ "$WORKER_STATE" != "running" ] || [ "$CH_HEALTH" != "healthy" ]; then
  echo "${RED}❌ worker 或 clickhouse 状态异常${NC}"
  exit 1
fi
ok "worker running + clickhouse healthy"

# 当前 kline 表行数(对比用)
echo ""
echo "${CYAN}─── 补数据前 · 当前 ClickHouse 行数 ───${NC}"
docker exec midas-clickhouse clickhouse-client --query "
SELECT market, symbol, period, count() AS rows
FROM kline
GROUP BY market, symbol, period
ORDER BY market, symbol, period
FORMAT PrettyCompactMonoBlock
" 2>&1 | head -30

# ============================================================
banner "2/4 · 跑 Python 回填脚本(带重试 + 指数退避)"
# ============================================================
warn "对 6 个缺口 (BTC×4 + 600519×2) 各重试最多 3 次 · 退避 5s/15s/30s"
warn "上游限流时整个步骤可能要 5-15 分钟 · 不要中断"

# Python 脚本通过 docker exec stdin 喂进容器(heredoc 在 bash 脚本内 · 不经终端粘贴 · 安全)
docker exec -i midas-worker python - <<'PY' 2>&1 | tee /tmp/backfill-gap-python.log
"""补 STEP 12 数据缺口 · 带重试 + 指数退避"""
import asyncio
import time
import sys

from tasks.data_ingest import _backfill_one

# (symbol, market, name, period, limit)
TARGETS = [
    # BTC 4 周期全要补(之前只 1d 拿到 20 行)
    ("BTC/USDT", "crypto", "Bitcoin",   "15m", 500),
    ("BTC/USDT", "crypto", "Bitcoin",   "1h",  500),
    ("BTC/USDT", "crypto", "Bitcoin",   "1d",  500),
    ("BTC/USDT", "crypto", "Bitcoin",   "1w",  500),
    # 600519 缺 1h/1w(15m/1d 已 OK · 不动)
    ("600519",   "cn",     "贵州茅台",  "1h",  500),
    ("600519",   "cn",     "贵州茅台",  "1w",  500),
]

MAX_ATTEMPTS = 3
BACKOFF = [5, 15, 30]   # 退避秒数

results = []
for symbol, market, name, period, limit in TARGETS:
    label = f"{symbol}/{market}@{period}"
    print(f"\n──── 开始 {label} ────", flush=True)
    success = False
    for attempt in range(MAX_ATTEMPTS):
        try:
            r = asyncio.run(_backfill_one(symbol, market, name, period, limit))
            rows = r.get("rows") if isinstance(r, dict) else "?"
            print(f"  ✓ {label}: attempt #{attempt+1} → rows={rows}", flush=True)
            results.append((label, "OK", rows, None))
            success = True
            break
        except Exception as e:
            err_msg = str(e)[:200]
            print(f"  ✗ {label}: attempt #{attempt+1} 失败 · {err_msg}", flush=True)
            if attempt < MAX_ATTEMPTS - 1:
                wait = BACKOFF[attempt]
                print(f"    退避 {wait}s 后重试...", flush=True)
                time.sleep(wait)
    if not success:
        results.append((label, "GIVEUP", 0, err_msg))
        print(f"  ⊘ {label}: 3 次都失败 · 放弃 · 继续下一个", flush=True)

# 汇总
print("\n" + "=" * 60, flush=True)
print("回填结果汇总", flush=True)
print("=" * 60, flush=True)
for label, status, rows, err in results:
    if status == "OK":
        print(f"  {status:8s} {label:30s} rows={rows}", flush=True)
    else:
        print(f"  {status:8s} {label:30s} {err}", flush=True)

ok_count = sum(1 for _, s, _, _ in results if s == "OK")
fail_count = sum(1 for _, s, _, _ in results if s == "GIVEUP")
print(f"\n  成功:{ok_count}/{len(TARGETS)} · 失败:{fail_count}/{len(TARGETS)}", flush=True)

# 不退出非零 · 让 bash 脚本继续到下一阶段
sys.exit(0)
PY

PYTHON_RC=$?
echo ""
if [ "$PYTHON_RC" = "0" ]; then
  ok "Python 回填脚本结束(部分失败也算正常完成 · 看上面汇总)"
else
  warn "Python 脚本异常退出码 $PYTHON_RC · 继续到最终统计"
fi

# ============================================================
banner "3/4 · 终态 · ClickHouse 各标的各周期最终行数"
# ============================================================
echo "${CYAN}─── 补完后 · 当前 ClickHouse 行数 ───${NC}"
docker exec midas-clickhouse clickhouse-client --query "
SELECT
  market,
  symbol,
  period,
  count() AS rows,
  min(ts) AS earliest,
  max(ts) AS latest
FROM kline
GROUP BY market, symbol, period
ORDER BY market, symbol, period
FORMAT PrettyCompactMonoBlock
" 2>&1 | head -40

# 缺口对比:哪些组合 < 100 行(可视为「数据严重不足」)
echo ""
echo "${CYAN}─── 缺口检查 · 行数 < 100 的组合(需关注)───${NC}"
docker exec midas-clickhouse clickhouse-client --query "
SELECT market, symbol, period, count() AS rows
FROM kline
GROUP BY market, symbol, period
HAVING rows < 100
ORDER BY rows ASC
FORMAT PrettyCompactMonoBlock
" 2>&1 | head -20

# ============================================================
banner "4/4 · 浏览器端验证建议"
# ============================================================
echo "  打开 https://midastrade.asia/workbench:"
echo "    · 切换标的到 BTC/USDT · 切 15m / 1h / 1d / 1w 4 周期"
echo "      → 应该都能显示 K 线(不是「数据源临时不可达」)"
echo "    · 切换到 600519 · 切 1h / 1w"
echo "      → 应该都能显示 K 线"
echo ""
echo "  如果还有缺口(脚本里看到 GIVEUP):"
echo "    1. 30 分钟后再跑一次 bash scripts/backfill-gap-data.sh"
echo "       (上游限流通常 15-30 min 解封)"
echo "    2. 或先在前端用别的标的展示 · M2 加自动补数据 worker"

echo ""
echo "${GREEN}╔═══════════════════════════════════════════════════════════${NC}"
echo "${GREEN}║  ✅ 数据补全脚本完成(看上面汇总判断哪些缺口仍在)${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  完整日志:/tmp/backfill-gap.log + /tmp/backfill-gap-python.log${NC}"
echo "${GREEN}╚═══════════════════════════════════════════════════════════${NC}"

exit 0  # 永远 0 · 让上层 git pull && bash 链路不中断
