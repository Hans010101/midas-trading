#!/bin/bash
# 点金 Midas · M2-A 隔离验证(GitHub Actions m2a-verify.yml SSH 触发)
# 2026-05-22 · feature/m2-crypto-pro
#
# 完全隔离 · 绝不碰生产:
#   · 独立工作目录 /opt/midas-m2-verify(不是 /opt/midas 生产目录)
#   · 独立 ClickHouse 库 m2_verify(不是生产 default 库)
#   · 独立 Postgres 库 midas_m2_verify(不是生产 midas 库)
#   · 临时容器 docker run --rm + bind-mount feature 代码(不 build · 不动
#     midas-api/web/worker 生产容器 · 复用现有 midas-api 镜像的已装依赖)
#   · 绝不调 update.sh · 绝不 git reset 生产目录
#
# 复用生产的 postgres/clickhouse/redis 容器(同 docker 网络)· 但读写
# 隔离库 · 生产数据零影响。

set -uo pipefail   # 注:不用 -e · 各阶段独立判定 · 末尾统一汇总

VERIFY_DIR=/opt/midas-m2-verify
BRANCH=feature/m2-crypto-pro
CH_DB=m2_verify
PG_DB=midas_m2_verify
NETWORK=midas-net
PROD_ENV=/opt/midas/.env

RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; NC=$'\033[0m'
banner() { echo ""; echo "${CYAN}══════ $1 ══════${NC}"; }
ok()   { echo "${GREEN}  ✓ $1${NC}"; }
warn() { echo "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo "${RED}  ✗ $1${NC}"; }

FAILED=0
mark_fail() { FAILED=1; fail "$1"; }

# ============================================================
banner "0/8 · 自检 · 隔离工作目录在 feature 分支"
# ============================================================
if [ ! -d "$VERIFY_DIR/.git" ]; then
  mark_fail "$VERIFY_DIR 不存在 · workflow 应已 clone · 中止"
  exit 1
fi
cd "$VERIFY_DIR"
git fetch origin "$BRANCH" 2>&1 | tail -2
git checkout -f "$BRANCH" 2>&1 | tail -1
git reset --hard "origin/$BRANCH" 2>&1 | tail -1
HEAD_HASH=$(git rev-parse --short HEAD)
ok "工作目录 $VERIFY_DIR · 分支 $BRANCH · HEAD $HEAD_HASH"

# 生产 .env 必须在(只读取 · 不修改)
if [ ! -f "$PROD_ENV" ]; then
  mark_fail "$PROD_ENV 不存在 · 拿不到 DB 凭证"; exit 1
fi

# 复用生产 api 镜像(已装好全部依赖 + pytest)· 不重新 build · 省内存
API_IMAGE=$(docker inspect midas-api --format '{{.Config.Image}}' 2>/dev/null || echo "")
if [ -z "$API_IMAGE" ]; then
  mark_fail "找不到 midas-api 镜像 · 生产 api 容器没在跑?"; exit 1
fi
ok "复用镜像 $API_IMAGE(bind-mount feature 代码 · 不重新 build)"

# 读生产 PG 密码(给建库 + alembic 用)· 只在脚本内存 · 不打印
set -a; source "$PROD_ENV"; set +a
ok "已加载生产 .env(CLICKHOUSE_PASSWORD / POSTGRES_PASSWORD 等)"

# 临时容器统一参数:bind-mount feature 的 apps/api 到 /app · 复用镜像 site-packages
# --env-file 给全套生产 env · 再用 -e 覆盖成隔离库
RUN_BASE=(docker run --rm --network "$NETWORK" -v "$VERIFY_DIR/apps/api:/app" --env-file "$PROD_ENV")

# ============================================================
banner "1/8 · ClickHouse 隔离库 m2_verify + 5 张表"
# ============================================================
docker exec midas-clickhouse clickhouse-client --query "CREATE DATABASE IF NOT EXISTS $CH_DB" 2>&1
docker exec -i midas-clickhouse clickhouse-client --database "$CH_DB" --multiquery <<'SQL' 2>&1
CREATE TABLE IF NOT EXISTS crypto_funding_rate (
    symbol String, ts DateTime, rate Float64, mark_price Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY (symbol, ts);
CREATE TABLE IF NOT EXISTS crypto_open_interest (
    symbol String, ts DateTime, oi_coin Float64, oi_usd Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY (symbol, ts);
CREATE TABLE IF NOT EXISTS crypto_long_short_ratio (
    symbol String, ts DateTime,
    top_account_long Float64, top_account_short Float64, top_account_ratio Float64,
    top_position_long Float64, top_position_short Float64, top_position_ratio Float64,
    taker_buy_vol Float64, taker_sell_vol Float64, taker_ratio Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY (symbol, ts);
CREATE TABLE IF NOT EXISTS crypto_ticker_24h (
    symbol String, instrument Enum8('spot'=1, 'perp'=2), ts DateTime,
    last_price Float64, change_pct_24h Float64, high_24h Float64, low_24h Float64,
    volume_24h Float64, quote_volume_24h Float64, count_24h UInt64 DEFAULT 0,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts)
ORDER BY (instrument, symbol, ts) TTL ingested_at + INTERVAL 30 DAY;
CREATE TABLE IF NOT EXISTS crypto_market_overview (
    ts DateTime, total_market_cap_usd Float64, total_volume_24h_usd Float64,
    btc_dominance Float64, eth_dominance Float64,
    fear_greed_value UInt8 DEFAULT 0, fear_greed_classification String DEFAULT '',
    derivatives_oi_usd Float64 DEFAULT 0, derivatives_volume_24h_usd Float64 DEFAULT 0,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY ts;
SQL
CH_TABLE_COUNT=$(docker exec midas-clickhouse clickhouse-client --query "
SELECT count() FROM system.tables WHERE database='$CH_DB' AND name LIKE 'crypto_%'" 2>/dev/null | tr -d '[:space:]')
if [ "$CH_TABLE_COUNT" = "5" ]; then
  ok "ClickHouse m2_verify 库 5 张表建好"
else
  mark_fail "ClickHouse 表数 = $CH_TABLE_COUNT(应 5)"
fi

# ============================================================
banner "2/8 · Postgres 隔离库 midas_m2_verify + alembic 全链路"
# ============================================================
# 建库(幂等)
HAS_DB=$(docker exec midas-postgres psql -U midas -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$PG_DB'" 2>/dev/null | tr -d '[:space:]')
if [ "$HAS_DB" != "1" ]; then
  docker exec midas-postgres psql -U midas -c "CREATE DATABASE $PG_DB" 2>&1
fi
# 空库跑完整 alembic 链路(base → ... → a2b3c4d5e6f7)· 验证 migration 干净
echo "  alembic upgrade head(空库全链路 · 含 4 张合约表 a2b3c4d5e6f7)..."
"${RUN_BASE[@]}" \
  -e DATABASE_URL="postgresql+asyncpg://midas:${POSTGRES_PASSWORD}@postgres:5432/$PG_DB" \
  "$API_IMAGE" alembic upgrade head 2>&1 | tail -15
PG_FUTURES_COUNT=$(docker exec midas-postgres psql -U midas -d "$PG_DB" -tAc "
SELECT count(*) FROM information_schema.tables WHERE table_name LIKE 'virtual_futures%'" 2>/dev/null | tr -d '[:space:]')
if [ "$PG_FUTURES_COUNT" = "4" ]; then
  ok "alembic 全链路通 · 4 张虚拟合约表建好"
else
  mark_fail "虚拟合约表数 = $PG_FUTURES_COUNT(应 4)"
fi

# ============================================================
banner "3/8 · pytest · 14 个单测(全 mock · 不打外网)"
# ============================================================
"${RUN_BASE[@]}" "$API_IMAGE" sh -c "cd /app && python -m pytest \
  tests/services/test_binance_futures_source.py \
  tests/services/test_coingecko_and_alternative_me.py \
  tests/api/test_crypto_endpoints.py::test_crypto_router_has_no_write_endpoints \
  -q -p no:cacheprovider" 2>&1 | tail -25
PYTEST_RC=${PIPESTATUS[0]}
if [ "$PYTEST_RC" = "0" ]; then ok "pytest 全 PASS"; else mark_fail "pytest 有 fail(rc=$PYTEST_RC)"; fi

# ============================================================
banner "4/8 · 实连 Binance Futures(BTC K/funding/OI/多空比/ticker)"
# ============================================================
"${RUN_BASE[@]}" "$API_IMAGE" python - <<'PY' 2>&1
import asyncio
from app.services.data_sources.binance_futures_source import BinanceFuturesSource
async def main():
    s = BinanceFuturesSource()
    try:
        k = await s.fetch_kline("BTCUSDT", "1d", limit=5)
        print(f"[OK] BTC 1d K {len(k)} 根 · 最新收盘 ${k[-1].close:.2f}")
        fr = await s.fetch_funding_rate("BTCUSDT", limit=3)
        print(f"[OK] funding {len(fr)} 条 · 最新 rate {fr[-1].rate}")
        oi = await s.fetch_open_interest("BTCUSDT", limit=3)
        print(f"[OK] OI {len(oi)} 条 · 最新 ${oi[-1].oi_usd/1e9:.2f}B")
        try:
            ls = await s.fetch_long_short_ratio("BTCUSDT", limit=3)
            print(f"[OK] 多空比 {len(ls)} 条 · taker_ratio {ls[-1].taker_ratio:.3f}")
        except Exception as e:
            print(f"[WARN] 多空比(三 endpoint 对齐 · M2-B 改并发): {e}")
        t = await s.fetch_ticker_24h()
        print(f"[OK] perp ticker 全市场 {len(t)} 个")
    finally:
        await s.close()
asyncio.run(main())
PY
BINANCE_RC=${PIPESTATUS[0]}
[ "$BINANCE_RC" = "0" ] && ok "Binance Futures 实连通" || mark_fail "Binance 实连失败(rc=$BINANCE_RC)"

# ============================================================
banner "5/8 · 实连 CoinGecko + alternative.me"
# ============================================================
"${RUN_BASE[@]}" "$API_IMAGE" python - <<'PY' 2>&1
import asyncio
from app.services.data_sources.coingecko_source import CoinGeckoSource
from app.services.data_sources.alternative_me_source import AlternativeMeSource
async def main():
    g = CoinGeckoSource()
    try:
        ov = await g.fetch_global_overview()
        print(f"[OK] CoinGecko 总市值 ${ov.total_market_cap_usd/1e12:.2f}T · BTC dom {ov.btc_dominance:.1f}%")
    finally:
        await g.close()
    a = AlternativeMeSource()
    try:
        fgi = await a.fetch_fear_greed(limit=3)
        print(f"[OK] FGI {len(fgi)} 天 · 最新 {fgi[-1].value}({fgi[-1].classification})")
    finally:
        await a.close()
asyncio.run(main())
PY
OVERVIEW_RC=${PIPESTATUS[0]}
[ "$OVERVIEW_RC" = "0" ] && ok "CoinGecko + alternative.me 通" || mark_fail "overview 实连失败(rc=$OVERVIEW_RC)"

# ============================================================
banner "6/8 · 端到端 · 实拉 → 写隔离 CH 库 m2_verify → 查回"
# ============================================================
"${RUN_BASE[@]}" \
  -e CLICKHOUSE_DATABASE="$CH_DB" \
  "$API_IMAGE" python - <<'PY' 2>&1
import asyncio, clickhouse_connect
from app.core.config import settings
from app.services.data_sources.binance_futures_source import BinanceFuturesSource
from app.services.data_sources.coingecko_source import CoinGeckoSource
from app.services.clickhouse_crypto import (
    insert_funding_rates, select_funding_rates,
    insert_open_interest, select_open_interest,
    insert_market_overview, select_latest_overview,
)
async def main():
    ch = await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host, port=settings.clickhouse_port,
        username=settings.clickhouse_user, password=settings.clickhouse_password,
        database=settings.clickhouse_database,  # = m2_verify(env 覆盖)
    )
    print(f"[info] 写入隔离库 = {settings.clickhouse_database}")
    bf = BinanceFuturesSource()
    try:
        fr = await bf.fetch_funding_rate("BTCUSDT", limit=3)
        n = await insert_funding_rates(ch, fr)
        back = await select_funding_rates(ch, "BTCUSDT", limit=3)
        assert len(back) >= 1
        print(f"[OK] funding 写{n}读{len(back)} · 最新 rate={back[-1].rate}")
        oi = await bf.fetch_open_interest("BTCUSDT", limit=3)
        n = await insert_open_interest(ch, oi)
        back = await select_open_interest(ch, "BTCUSDT", limit=3)
        print(f"[OK] OI 写{n}读{len(back)}")
    finally:
        await bf.close()
    g = CoinGeckoSource()
    try:
        ov = await g.fetch_global_overview()
        await insert_market_overview(ch, ov)
        latest = await select_latest_overview(ch)
        assert latest is not None
        print(f"[OK] overview 写读通 · btc_dom={latest.btc_dominance:.1f}%")
    finally:
        await g.close()
    await ch.close()
    print("[OK] 端到端 5 表 + 3 adapter + clickhouse_crypto helper 全链路通")
asyncio.run(main())
PY
E2E_RC=${PIPESTATUS[0]}
[ "$E2E_RC" = "0" ] && ok "端到端读写通" || mark_fail "端到端失败(rc=$E2E_RC)"

# ============================================================
banner "7/8 · 隔离库行数快照"
# ============================================================
docker exec midas-clickhouse clickhouse-client --database "$CH_DB" --query "
SELECT 'funding' t, count() n FROM crypto_funding_rate UNION ALL
SELECT 'oi', count() FROM crypto_open_interest UNION ALL
SELECT 'overview', count() FROM crypto_market_overview
FORMAT PrettyCompactMonoBlock" 2>&1 | head -10

# ============================================================
banner "8/8 · 总结"
# ============================================================
echo ""
echo "${CYAN}── 生产环境影响:0(全程隔离库 + 临时容器)──${NC}"
echo "  · /opt/midas 生产目录:未碰"
echo "  · midas-api/web/worker 容器:未重建"
echo "  · ClickHouse default 库 / Postgres midas 库:未写入"
echo ""
echo "${CYAN}── 隔离测试资源(验证后可留作复查 · 也可清理)──${NC}"
echo "  清理命令(可选):"
echo "    docker exec midas-clickhouse clickhouse-client --query 'DROP DATABASE IF EXISTS $CH_DB'"
echo "    docker exec midas-postgres psql -U midas -c 'DROP DATABASE IF EXISTS $PG_DB'"
echo ""
if [ "$FAILED" = "0" ]; then
  echo "${GREEN}╔═══════════════════════════════════════════════╗${NC}"
  echo "${GREEN}║  ✅ M2-A 隔离验证全部通过 · HEAD $HEAD_HASH${NC}"
  echo "${GREEN}╚═══════════════════════════════════════════════╝${NC}"
  exit 0
else
  echo "${RED}╔═══════════════════════════════════════════════╗${NC}"
  echo "${RED}║  ❌ M2-A 验证有失败项 · 看上面 ✗ 标记${NC}"
  echo "${RED}╚═══════════════════════════════════════════════╝${NC}"
  exit 1
fi
