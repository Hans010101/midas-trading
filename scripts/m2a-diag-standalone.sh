#!/bin/bash
# 点金 Midas · M2-A 逐层诊断 · 单文件自包含 · 服务器直接跑(无 workflow / 无 worktree)
#
# 跑法(一行 · 总是拉最新 · 不用手动粘贴长脚本):
#   cd /opt/midas && git fetch origin feature/m2-crypto-pro && \
#     git show origin/feature/m2-crypto-pro:scripts/m2a-diag-standalone.sh > /tmp/m2a-diag.sh && \
#     bash /tmp/m2a-diag.sh 2>&1 | tee /tmp/m2a-diag.log
#
# 隔离(生产零影响):
#   · 用 git archive 把 feature 代码导出到 /tmp/m2a-diag-code(不 clone / 不 worktree /
#     不动 /opt/midas 工作区)
#   · 独立 ClickHouse 测试库 m2_verify_diag(不碰生产 default 库)
#   · 临时容器 docker run --rm + bind-mount feature 代码(复用现有 midas-api 镜像 ·
#     不重新 build · 不动生产 api/web/worker 容器)
#   · 绝不调 update.sh
#
# 你不需要改任何变量 · 全部自动推导(镜像名 / 凭证 / host 都从现有环境取)。
# 末尾打印 [VERDICT] 那一行 = 断点结论。

set -uo pipefail

CYAN=$'\033[1;36m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; RED=$'\033[1;31m'; NC=$'\033[0m'

REPO=/opt/midas
BRANCH=feature/m2-crypto-pro
CODE_DIR=/tmp/m2a-diag-code
CH_DB=m2_verify_diag
PROD_ENV=/opt/midas/.env

echo "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo "${CYAN}  M2-A 逐层诊断 · $(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
echo "${CYAN}══════════════════════════════════════════════════════════════${NC}"

# ── 0. 前置 ──
if [ ! -d "$REPO/.git" ]; then echo "${RED}❌ $REPO 不是 git 仓库${NC}"; exit 1; fi
if [ ! -f "$PROD_ENV" ]; then echo "${RED}❌ $PROD_ENV 不存在${NC}"; exit 1; fi

# ── 1. fetch 最新 feature(用 /opt/midas 现有凭证 · git fetch 在已有仓库可用)──
echo ""
echo "${CYAN}── 1. fetch 最新 feature 分支 ──${NC}"
cd "$REPO"
git fetch --force origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
TARGET=$(git rev-parse "refs/remotes/origin/$BRANCH")
echo "目标 feature commit: $TARGET"
git log --oneline -1 "$TARGET"

# ── 2. git archive 导出 feature 代码到临时目录(不 clone / 不 worktree)──
echo ""
echo "${CYAN}── 2. 导出 feature 代码到 $CODE_DIR(git archive)──${NC}"
rm -rf "$CODE_DIR"; mkdir -p "$CODE_DIR"
git archive "$TARGET" | tar -x -C "$CODE_DIR"
if grep -q "VERDICT" "$CODE_DIR/scripts/m2a-verify-ci.sh" 2>/dev/null; then
  echo "${GREEN}✓ 确认导出的是诊断版代码(scripts 含 VERDICT)${NC}"
else
  echo "${YELLOW}⚠ 导出代码没找到 VERDICT 标记 · 仍用本脚本内置探针继续${NC}"
fi
echo "关键文件检查:"
ls -la "$CODE_DIR/apps/api/app/services/clickhouse_crypto.py" "$CODE_DIR/apps/api/app/services/data_sources/binance_futures_source.py" 2>&1 | sed 's/^/  /'

# ── 3. 读生产 .env(凭证 · 不打印值)+ 取镜像名 ──
set -a; source "$PROD_ENV"; set +a
API_IMAGE=$(docker inspect midas-api --format '{{.Config.Image}}' 2>/dev/null || echo "")
if [ -z "$API_IMAGE" ]; then echo "${RED}❌ 找不到 midas-api 镜像${NC}"; exit 1; fi
echo ""
echo "${CYAN}── 3. 复用镜像 $API_IMAGE · 凭证已从 .env 加载 ──${NC}"

# ── 4. 建独立 CH 测试库 + funding 表 ──
echo ""
echo "${CYAN}── 4. 建独立 ClickHouse 测试库 $CH_DB + crypto_funding_rate 表 ──${NC}"
docker exec midas-clickhouse clickhouse-client --query "CREATE DATABASE IF NOT EXISTS $CH_DB" 2>&1
docker exec -i midas-clickhouse clickhouse-client --database "$CH_DB" --multiquery <<'SQL' 2>&1
CREATE TABLE IF NOT EXISTS crypto_funding_rate (
    symbol String, ts DateTime, rate Float64, mark_price Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY (symbol, ts);
SQL
# 清空可能的旧诊断数据 · 保证本次干净(只清测试库 · 不碰生产)
docker exec midas-clickhouse clickhouse-client --database "$CH_DB" --query "TRUNCATE TABLE crypto_funding_rate" 2>&1 || true
echo "测试库就绪 · 表已清空"

# ── 5. 逐层探针(临时容器 · bind-mount feature 代码 · 写隔离库)──
echo ""
echo "${CYAN}── 5. 逐层探针(A: helper insert / B: fresh 连接 / C: raw SQL 对照)──${NC}"
docker run --rm --network midas-net -v "$CODE_DIR/apps/api:/app" \
  --env-file "$PROD_ENV" -e CLICKHOUSE_DATABASE="$CH_DB" \
  "$API_IMAGE" python - <<'PY' 2>&1
import asyncio, traceback
import clickhouse_connect
from app.core.config import settings
from app.services.data_sources.binance_futures_source import BinanceFuturesSource
from app.services.clickhouse_crypto import insert_funding_rates

DB = settings.clickhouse_database
print(f"[info] settings.clickhouse_database = {DB}")
print(f"[info] CLICKHOUSE_HOST = {settings.clickhouse_host} · USER = {settings.clickhouse_user}")
if DB != "m2_verify_diag":
    print(f"[FATAL] 写入库不是 m2_verify_diag 而是 '{DB}' · -e 覆盖未生效")
    raise SystemExit(2)


def fresh_sync_client():
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host, port=settings.clickhouse_port,
        username=settings.clickhouse_user, password=settings.clickhouse_password,
        database=DB,
    )


async def write_via_helper():
    wch = await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host, port=settings.clickhouse_port,
        username=settings.clickhouse_user, password=settings.clickhouse_password,
        database=DB,
    )
    bf = BinanceFuturesSource()
    try:
        fr = await bf.fetch_funding_rate("BTCUSDT", limit=3)
        print(f"[A.fetch] funding 实拉 {len(fr)} 条")
        if fr:
            print(f"[A.sample] 第1条: symbol={fr[0].symbol} ts={fr[0].ts} rate={fr[0].rate} mark={fr[0].mark_price}")
        n = await insert_funding_rates(wch, fr)
        print(f"[A.insert] insert_funding_rates 返回 n={n}")
        same = (await wch.query("SELECT count() FROM crypto_funding_rate")).result_rows[0][0]
        print(f"[A.same-conn count] crypto_funding_rate = {same}")
        return len(fr), n, int(same)
    finally:
        await bf.close()
        await wch.close()


try:
    fetched, n, same_count = asyncio.run(write_via_helper())
except Exception:
    print("[A.ERROR] helper 写入路径抛异常:")
    traceback.print_exc()
    raise SystemExit(3)

# 探针 B:fresh 连接(写连接已关)
c = fresh_sync_client()
fresh_count = int(c.command("SELECT count() FROM crypto_funding_rate"))
print(f"[B.fresh-conn count] crypto_funding_rate = {fresh_count}")

verdict = "UNKNOWN"
if n > 0 and same_count > 0 and fresh_count > 0:
    verdict = "PASS · helper insert 真持久化 · 跨连接可见 · 数据层 OK(之前是阶段7查询身份问题)"
elif n > 0 and same_count > 0 and fresh_count == 0:
    print("[C.diag] helper insert 返回 n>0 且同连接可见 · 但 fresh 连接=0 · raw SQL INSERT 对照...")
    try:
        c.command(
            "INSERT INTO crypto_funding_rate (symbol, ts, rate, mark_price) "
            "VALUES ('TESTRAW', now(), 0.0001, 60000)"
        )
        raw = int(c.command("SELECT count() FROM crypto_funding_rate WHERE symbol='TESTRAW'"))
        print(f"[C.raw-insert] raw SQL INSERT 后 count(TESTRAW) = {raw}")
        if raw > 0:
            verdict = "BUG=clickhouse_crypto.insert_*(clickhouse-connect insert() 用法)· raw SQL 能持久化但 helper 不能"
        else:
            verdict = "BUG=表/引擎/连接层(raw SQL 也不持久化)"
    except Exception:
        print("[C.raw-insert ERROR]")
        traceback.print_exc()
        verdict = "BUG=raw INSERT 也异常 · 表/权限层"
elif n > 0 and same_count == 0:
    verdict = "BUG=insert 返回 n>0 但同连接立刻 count=0 · insert 实际是 no-op"
else:
    verdict = f"BUG=insert 返回 n={n}(fetch={fetched})· 采集或入库前置断"

print("")
print("════════════════════════════════════════════════════════════")
print(f"[VERDICT] {verdict}")
print("════════════════════════════════════════════════════════════")
c.close()
PY

# ── 6. 清理提示 ──
echo ""
echo "${CYAN}── 6. 完毕 ──${NC}"
echo "上面 [VERDICT] 那一行 = 断点结论 · 整段(含 [A.*]/[B.*]/[C.*]/[VERDICT])贴回给 Claude。"
echo ""
echo "清理(可选 · 只清诊断测试库 + 临时代码 · 不碰生产):"
echo "  docker exec midas-clickhouse clickhouse-client --query 'DROP DATABASE IF EXISTS $CH_DB'"
echo "  rm -rf $CODE_DIR"
echo ""
echo "${GREEN}诊断结束 · 生产环境零影响(独立库 $CH_DB + 临时容器 + git archive 导出)${NC}"
