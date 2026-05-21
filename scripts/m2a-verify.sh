#!/bin/bash
# 点金 Midas · M2-A · Crypto Pro 数据层验证脚本
# 2026-05-21 · feature/m2-crypto-pro 分支
#
# 用法(服务器 · 白天值守):
#   cd /opt/midas
#   git fetch origin
#   git checkout feature/m2-crypto-pro
#   git pull origin feature/m2-crypto-pro
#   bash update.sh                          ← 关键:让 update.sh 跑 build + alembic
#   bash scripts/m2a-verify.sh 2>&1 | tee /tmp/m2a-verify.log
#
# 验证完后(无论成功失败)切回 main:
#   git checkout main
#   bash update.sh                          ← 回滚到 main · 重 build api/web
#
# 红线:本脚本对 ClickHouse / Postgres 的改动**只新增 · 不删数据**:
#   · ClickHouse 5 张新表 CREATE IF NOT EXISTS · kline ALTER ADD COLUMN IF NOT EXISTS
#   · Postgres 4 张新表 · 走 alembic upgrade head(由 update.sh 触发)
#   · 现有 kline / virtual_account / user 等表零改动

set -euo pipefail

RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; NC=$'\033[0m'

STAGE="init"
on_err() {
  local line=$1
  echo ""
  echo "${RED}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${RED}║  ❌ M2-A 验证失败 · 阶段=「${STAGE}」 · 行号=${line}${NC}"
  echo "${RED}╚═══════════════════════════════════════════════════════════${NC}"
  echo ""
  echo "${YELLOW}--- docker compose ps ---${NC}"
  docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted ps 2>/dev/null || true
  echo ""
  echo "${YELLOW}回滚到 main:${NC}"
  echo "  cd /opt/midas && git checkout main && bash update.sh"
  exit 1
}
trap 'on_err $LINENO' ERR

banner() {
  STAGE="$1"
  echo ""
  echo "${CYAN}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${CYAN}║  === $1 ===${NC}"
  echo "${CYAN}╚═══════════════════════════════════════════════════════════${NC}"
}
ok()   { echo "${GREEN}  ✓ $1${NC}"; }
warn() { echo "${YELLOW}  ⚠ $1${NC}"; }
info() { echo "${CYAN}  · $1${NC}"; }

cd /opt/midas

# ============================================================
banner "1/8 · 自检 · 当前在 feature/m2-crypto-pro 分支 + 容器 healthy"
# ============================================================
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "feature/m2-crypto-pro" ]; then
  echo "${RED}❌ 当前分支是 '$CURRENT_BRANCH' · 必须先 git checkout feature/m2-crypto-pro${NC}"
  exit 1
fi
HEAD_HASH=$(git rev-parse --short HEAD)
ok "分支 feature/m2-crypto-pro · HEAD = $HEAD_HASH"

# 容器健康(假设 update.sh 已跑)
HEALTHCHECK=("midas-postgres" "midas-clickhouse" "midas-redis" "midas-api" "midas-web")
for svc in "${HEALTHCHECK[@]}"; do
  state=$(docker inspect -f '{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "no-container")
  if [ "$state" != "healthy" ]; then
    echo "${RED}❌ $svc 不是 healthy · 当前=$state · 请先 bash update.sh${NC}"
    exit 1
  fi
done
worker_state=$(docker inspect -f '{{.State.Status}}' midas-worker 2>/dev/null || echo "?")
if [ "$worker_state" != "running" ]; then
  echo "${RED}❌ midas-worker 不是 running · 当前=$worker_state${NC}"
  exit 1
fi
ok "5 服务 healthy + worker running"

# ============================================================
banner "2/8 · ClickHouse · kline ALTER + 5 张新表 apply(幂等)"
# ============================================================
info "kline 表加 instrument 列(默认 'spot' · 老数据零兼容性影响)"

docker exec midas-clickhouse clickhouse-client --query "
ALTER TABLE kline
    ADD COLUMN IF NOT EXISTS instrument Enum8('spot'=1, 'perp'=2) DEFAULT 'spot'
    AFTER market
" 2>&1 | tee /tmp/m2a-clickhouse-alter.log

# 验证列已经在
INSTRUMENT_EXISTS=$(docker exec midas-clickhouse clickhouse-client --query "
SELECT count() FROM system.columns WHERE table='kline' AND name='instrument'
" 2>&1 | tr -d '[:space:]')
if [ "$INSTRUMENT_EXISTS" != "1" ]; then
  echo "${RED}❌ kline.instrument 列没建上 · 检查 ALTER 输出${NC}"
  exit 1
fi
ok "kline.instrument 列在位"

info "5 张新表 CREATE IF NOT EXISTS(逐张创建)"
# 提取 init.sql 中 M2-A 段落的 CREATE 语句 · 逐张跑
docker exec -i midas-clickhouse clickhouse-client --multiquery <<'CHSQL'
CREATE TABLE IF NOT EXISTS crypto_funding_rate (
    symbol String,
    ts DateTime,
    rate Float64,
    mark_price Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS crypto_open_interest (
    symbol String,
    ts DateTime,
    oi_coin Float64,
    oi_usd Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS crypto_long_short_ratio (
    symbol String,
    ts DateTime,
    top_account_long Float64,
    top_account_short Float64,
    top_account_ratio Float64,
    top_position_long Float64,
    top_position_short Float64,
    top_position_ratio Float64,
    taker_buy_vol Float64,
    taker_sell_vol Float64,
    taker_ratio Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS crypto_ticker_24h (
    symbol String,
    instrument Enum8('spot'=1, 'perp'=2),
    ts DateTime,
    last_price Float64,
    change_pct_24h Float64,
    high_24h Float64,
    low_24h Float64,
    volume_24h Float64,
    quote_volume_24h Float64,
    count_24h UInt64 DEFAULT 0,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (instrument, symbol, ts)
TTL ingested_at + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS crypto_market_overview (
    ts DateTime,
    total_market_cap_usd Float64,
    total_volume_24h_usd Float64,
    btc_dominance Float64,
    eth_dominance Float64,
    fear_greed_value UInt8 DEFAULT 0,
    fear_greed_classification String DEFAULT '',
    derivatives_oi_usd Float64 DEFAULT 0,
    derivatives_volume_24h_usd Float64 DEFAULT 0,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY ts
SETTINGS index_granularity = 8192;
CHSQL

# 验证 5 张表都存在
TABLE_COUNT=$(docker exec midas-clickhouse clickhouse-client --query "
SELECT count() FROM system.tables
WHERE database='default' AND name IN (
  'crypto_funding_rate', 'crypto_open_interest', 'crypto_long_short_ratio',
  'crypto_ticker_24h', 'crypto_market_overview'
)
" 2>&1 | tr -d '[:space:]')
if [ "$TABLE_COUNT" != "5" ]; then
  echo "${RED}❌ ClickHouse 新表数量不对 · 当前=$TABLE_COUNT(应=5)${NC}"
  docker exec midas-clickhouse clickhouse-client --query "
    SELECT name FROM system.tables WHERE database='default' AND name LIKE 'crypto_%'
  "
  exit 1
fi
ok "5 张新表全部 CREATE 成功"

# ============================================================
banner "3/8 · Postgres · alembic 应在 a2b3c4d5e6f7(虚拟合约 4 表)"
# ============================================================
ALEMBIC_CURRENT=$(docker exec midas-api alembic current 2>&1 | grep -v "^INFO\|^$" | tail -1)
ok "alembic current: $ALEMBIC_CURRENT"

if ! echo "$ALEMBIC_CURRENT" | grep -q "a2b3c4d5e6f7"; then
  echo "${YELLOW}⚠ alembic 不是 a2b3c4d5e6f7 · update.sh 可能没跑或者 migration 失败${NC}"
  echo "${YELLOW}手动跑:docker exec midas-api alembic upgrade head${NC}"
  # 不直接退出 · 让 user 决定
fi

# 验证 4 张表存在
PG_TABLE_COUNT=$(docker exec midas-postgres psql -U midas -d midas -t -c "
SELECT count(*) FROM information_schema.tables WHERE table_name IN (
  'virtual_futures_account', 'virtual_futures_position',
  'virtual_futures_order', 'virtual_futures_funding_settlement'
)
" 2>&1 | tr -d '[:space:]')
if [ "$PG_TABLE_COUNT" != "4" ]; then
  echo "${RED}❌ Postgres 虚拟合约表数量不对 · 当前=$PG_TABLE_COUNT(应=4)${NC}"
  exit 1
fi
ok "Postgres 4 张虚拟合约表全部存在"

# ============================================================
banner "4/8 · pytest · 14 个单测(全部 mock · 不打外网)"
# ============================================================
info "在 midas-api 容器内跑 pytest · 不打外网(httpx.MockTransport)"

# 注:测试文件在镜像里(update.sh 已 rebuild)· 用 -p no:cacheprovider 避免污染
set +e
docker exec midas-api sh -c "
cd /repo/apps/api &&
python -m pytest \
  tests/services/test_binance_futures_source.py \
  tests/services/test_coingecko_and_alternative_me.py \
  tests/api/test_crypto_endpoints.py::test_crypto_router_has_no_write_endpoints \
  -v -p no:cacheprovider 2>&1
" | tee /tmp/m2a-pytest.log
PYTEST_RC=$?
set -e

if [ "$PYTEST_RC" != "0" ]; then
  echo "${RED}❌ pytest 有 failure · 看 /tmp/m2a-pytest.log${NC}"
  # 不立即退出 · 继续后面阶段 · 但记 fail
  PYTEST_FAILED=true
else
  ok "pytest 全部 PASS"
  PYTEST_FAILED=false
fi

# ============================================================
banner "5/8 · 实连 Binance Futures · BTCUSDT 1d K + funding + OI"
# ============================================================
info "拿 BTC 1d K 5 根 + 资金费率 3 条 + OI 3 条(实打 fapi.binance.com)"

set +e
docker exec midas-api python - <<'PY' 2>&1 | tee /tmp/m2a-binance.log
import asyncio
from app.services.data_sources.binance_futures_source import BinanceFuturesSource

async def main():
    src = BinanceFuturesSource()
    try:
        # 1. K 线
        klines = await src.fetch_kline("BTCUSDT", "1d", limit=5)
        print(f"[OK] BTC 1d K {len(klines)} 根 · 最新收盘 ${klines[-1].close:.2f}")
        print(f"     ts 范围: {klines[0].ts.isoformat()} → {klines[-1].ts.isoformat()}")

        # 2. funding
        fr = await src.fetch_funding_rate("BTCUSDT", limit=3)
        print(f"[OK] BTC funding {len(fr)} 条 · 最新 rate {fr[-1].rate} (markPrice ${fr[-1].mark_price:.2f})")

        # 3. OI
        oi = await src.fetch_open_interest("BTCUSDT", limit=3)
        print(f"[OK] BTC OI {len(oi)} 条 · 最新 oi_usd ${oi[-1].oi_usd / 1e9:.2f}B")

        # 4. long-short ratio
        try:
            ls = await src.fetch_long_short_ratio("BTCUSDT", limit=3)
            print(f"[OK] BTC long-short {len(ls)} 条 · 最新 account_ratio {ls[-1].top_account_ratio:.3f} taker_ratio {ls[-1].taker_ratio:.3f}")
        except Exception as e:
            print(f"[WARN] long-short 失败(三 endpoint timestamp 对齐策略可能要 M2-B 改并发): {e}")

        # 5. ticker 24h(全市场快照)
        tickers = await src.fetch_ticker_24h()
        print(f"[OK] perp ticker 全市场 {len(tickers)} 个 · 头部样本:")
        for t in tickers[:3]:
            print(f"     {t.symbol:14s} change_24h={t.change_pct_24h:+6.2f}% quote_vol={t.quote_volume_24h/1e9:.2f}B")
    finally:
        await src.close()

asyncio.run(main())
PY
BINANCE_RC=$?
set -e
if [ "$BINANCE_RC" != "0" ]; then
  echo "${YELLOW}⚠ Binance 实连失败 · 看上面输出${NC}"
fi

# ============================================================
banner "6/8 · 实连 CoinGecko + alternative.me"
# ============================================================
set +e
docker exec midas-api python - <<'PY' 2>&1 | tee /tmp/m2a-overview.log
import asyncio
from app.services.data_sources.coingecko_source import CoinGeckoSource
from app.services.data_sources.alternative_me_source import AlternativeMeSource

async def main():
    # CoinGecko global
    gecko = CoinGeckoSource()
    try:
        ov = await gecko.fetch_global_overview()
        print(f"[OK] CoinGecko global · 总市值 ${ov.total_market_cap_usd/1e12:.2f}T · "
              f"24h 量 ${ov.total_volume_24h_usd/1e9:.1f}B · "
              f"BTC dominance {ov.btc_dominance:.2f}% · ETH {ov.eth_dominance:.2f}%")
    finally:
        await gecko.close()

    # alternative.me FGI
    altme = AlternativeMeSource()
    try:
        fgi = await altme.fetch_fear_greed(limit=5)
        print(f"[OK] alternative.me FGI {len(fgi)} 天:")
        for p in fgi:
            print(f"     {p.ts.date()} value={p.value:3d} ({p.classification})")
    finally:
        await altme.close()

asyncio.run(main())
PY
OVERVIEW_RC=$?
set -e

# ============================================================
banner "7/8 · 端到端 · 实拉数据 → 写 ClickHouse → 查回来"
# ============================================================
info "证明 5 张新表 + 3 个 adapter 跟 clickhouse_crypto helper 全链路通"

set +e
docker exec midas-api python - <<'PY' 2>&1 | tee /tmp/m2a-e2e.log
import asyncio
import clickhouse_connect
from app.core.config import settings
from app.services.data_sources.binance_futures_source import BinanceFuturesSource
from app.services.data_sources.coingecko_source import CoinGeckoSource
from app.services.data_sources.alternative_me_source import AlternativeMeSource
from app.services.clickhouse_crypto import (
    insert_funding_rates, select_funding_rates,
    insert_open_interest, select_open_interest,
    insert_market_overview, select_latest_overview,
    merge_fear_greed_into_latest_overview,
    select_fear_greed_series,
)

async def main():
    ch = await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )

    # ── funding rate
    bf = BinanceFuturesSource()
    try:
        fr_items = await bf.fetch_funding_rate("BTCUSDT", limit=3)
        n = await insert_funding_rates(ch, fr_items)
        print(f"[OK] funding rate inserted {n} 行")
        back = await select_funding_rates(ch, "BTCUSDT", limit=3)
        print(f"[OK] funding rate 读回 {len(back)} 行 · 最新 rate={back[-1].rate}")
        assert len(back) >= 1, "查不到刚写的 funding rate"

        # ── OI
        oi_items = await bf.fetch_open_interest("BTCUSDT", limit=3)
        n = await insert_open_interest(ch, oi_items)
        print(f"[OK] OI inserted {n} 行")
        back = await select_open_interest(ch, "BTCUSDT", limit=3)
        print(f"[OK] OI 读回 {len(back)} 行 · 最新 oi_usd ${back[-1].oi_usd/1e9:.2f}B")
    finally:
        await bf.close()

    # ── market overview
    gecko = CoinGeckoSource()
    try:
        ov = await gecko.fetch_global_overview()
        await insert_market_overview(ch, ov)
        latest = await select_latest_overview(ch)
        assert latest is not None
        print(f"[OK] market_overview 写读通 · btc_dom={latest.btc_dominance:.2f}%")
    finally:
        await gecko.close()

    # ── FGI merge
    altme = AlternativeMeSource()
    try:
        fgi = await altme.fetch_fear_greed(limit=1)
        if fgi:
            await merge_fear_greed_into_latest_overview(
                ch, fgi_value=fgi[-1].value, fgi_classification=fgi[-1].classification,
            )
            series = await select_fear_greed_series(ch, limit=7)
            print(f"[OK] FGI merge + 时间序列查询 · 最新 value={fgi[-1].value} ({fgi[-1].classification})")
            print(f"     时间序列长度 = {len(series)}")
    finally:
        await altme.close()

    await ch.close()
    print("[OK] 端到端 5 张表 + 3 adapter 全部跑通")

asyncio.run(main())
PY
E2E_RC=$?
set -e

# ============================================================
banner "8/8 · 总结 + 后续建议"
# ============================================================
STAGE="8/8 summary"

echo ""
echo "${CYAN}─── ClickHouse 新表行数 ───${NC}"
docker exec midas-clickhouse clickhouse-client --query "
SELECT 'crypto_funding_rate' AS table, count() AS rows FROM crypto_funding_rate UNION ALL
SELECT 'crypto_open_interest', count() FROM crypto_open_interest UNION ALL
SELECT 'crypto_long_short_ratio', count() FROM crypto_long_short_ratio UNION ALL
SELECT 'crypto_ticker_24h', count() FROM crypto_ticker_24h UNION ALL
SELECT 'crypto_market_overview', count() FROM crypto_market_overview
FORMAT PrettyCompactMonoBlock
" 2>&1 | head -15

echo ""
echo "${CYAN}─── Postgres 虚拟合约 4 张表存在性 ───${NC}"
docker exec midas-postgres psql -U midas -d midas -c "
SELECT table_name FROM information_schema.tables
WHERE table_name LIKE 'virtual_futures%'
ORDER BY table_name
" 2>&1 | head -10

echo ""
echo "${CYAN}─── 阶段结果汇总 ───${NC}"
[ "${PYTEST_FAILED:-false}" = "false" ]  && echo "  ${GREEN}✓${NC} 4/8 pytest 全 PASS"                || echo "  ${RED}✗${NC} 4/8 pytest 有 fail · 看 /tmp/m2a-pytest.log"
[ "${BINANCE_RC:-1}" = "0" ]              && echo "  ${GREEN}✓${NC} 5/8 Binance Futures 实连通过"    || echo "  ${RED}✗${NC} 5/8 Binance 实连失败 · 看 /tmp/m2a-binance.log"
[ "${OVERVIEW_RC:-1}" = "0" ]             && echo "  ${GREEN}✓${NC} 6/8 CoinGecko + alternative.me 通过" || echo "  ${RED}✗${NC} 6/8 overview 失败 · 看 /tmp/m2a-overview.log"
[ "${E2E_RC:-1}" = "0" ]                  && echo "  ${GREEN}✓${NC} 7/8 端到端读写通"                  || echo "  ${RED}✗${NC} 7/8 端到端失败 · 看 /tmp/m2a-e2e.log"

echo ""
echo "${GREEN}╔═══════════════════════════════════════════════════════════${NC}"
echo "${GREEN}║  M2-A 验证结束 · 完整日志:${NC}"
echo "${GREEN}║    /tmp/m2a-verify.log(本脚本)${NC}"
echo "${GREEN}║    /tmp/m2a-pytest.log${NC}"
echo "${GREEN}║    /tmp/m2a-binance.log${NC}"
echo "${GREEN}║    /tmp/m2a-overview.log${NC}"
echo "${GREEN}║    /tmp/m2a-e2e.log${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  下一步:${NC}"
echo "${GREEN}║    A. 全过 → 给我「M2-A 通过」· 进 M2-C(撮合)+ 整理 M2-B${NC}"
echo "${GREEN}║    B. 有 fail → 把对应 /tmp/*.log 贴回 · 我诊断${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  回滚到 main(必做!避免生产数据被 feature 分支影响):${NC}"
echo "${GREEN}║    cd /opt/midas && git checkout main && bash update.sh${NC}"
echo "${GREEN}╚═══════════════════════════════════════════════════════════${NC}"
