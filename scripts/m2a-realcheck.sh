#!/bin/bash
# 点金 Midas · M2-A 极简真实核查 · 一锤定音"真实采集后 count 到底 >0 还是 0"
#
# 跑法(一行 · git 把脚本写到 /tmp 再执行 · 稳妥):
#   cd /opt/midas && git fetch origin feature/m2-crypto-pro && \
#     git show origin/feature/m2-crypto-pro:scripts/m2a-realcheck.sh > /tmp/m2a-realcheck.sh && \
#     bash /tmp/m2a-realcheck.sh 2>&1 | tee /tmp/m2a-realcheck.log
#
# 思路:用 worker 平时的客户端配置(_get_ch_client · session_timezone=UTC)·
#       调 worker 平时的采集入口(_funding_rate_refresh_async 等)· 写 default 库 ·
#       再用同配置 count。采集和 count 同库同配置 · 杜绝"写A库读B库"歧义。
#
# 边界:
#   · 只碰生产 default 库(建 3 张 crypto 表 + 写真实行)· M2-C 部署本来也要建这些表
#   · feature 代码注入运行中的 worker 容器(增量 · `docker restart midas-worker` 即还原)
#   · 不调 update.sh · 不 worktree · 不起临时容器 · 不动 default 库以外任何东西

set -e
cd /opt/midas
git fetch --force origin "+refs/heads/feature/m2-crypto-pro:refs/remotes/origin/feature/m2-crypto-pro"
T=$(git rev-parse refs/remotes/origin/feature/m2-crypto-pro)
echo "════ feature commit: $T ════"; git log --oneline -1 "$T"

# 1. 把 feature 的 worker/api 代码注入运行中的 worker(覆盖 /repo/apps · 重启即还原)
echo "── 注入 feature 代码到 midas-worker ──"
git archive "$T" apps/api apps/worker | docker exec -i midas-worker tar -x -C /repo
echo "  done"

# 2. default 库建 3 张待查表(CREATE IF NOT EXISTS · 不删任何东西 · M2-C 部署也要建)
echo "── default 库确保 3 张 crypto 表存在 ──"
docker exec -i midas-clickhouse clickhouse-client --multiquery <<'SQL'
CREATE TABLE IF NOT EXISTS crypto_funding_rate (symbol String, ts DateTime, rate Float64, mark_price Float64, ingested_at DateTime DEFAULT now()) ENGINE=ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY (symbol, ts);
CREATE TABLE IF NOT EXISTS crypto_open_interest (symbol String, ts DateTime, oi_coin Float64, oi_usd Float64, ingested_at DateTime DEFAULT now()) ENGINE=ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY (symbol, ts);
CREATE TABLE IF NOT EXISTS crypto_market_overview (ts DateTime, total_market_cap_usd Float64, total_volume_24h_usd Float64, btc_dominance Float64, eth_dominance Float64, fear_greed_value UInt8 DEFAULT 0, fear_greed_classification String DEFAULT '', derivatives_oi_usd Float64 DEFAULT 0, derivatives_volume_24h_usd Float64 DEFAULT 0, ingested_at DateTime DEFAULT now()) ENGINE=ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY ts;
SQL
echo "  done"

# 3. 真实采集 + count(≤15 行核心 · 全用 worker 自己的采集入口 + _get_ch_client)
echo "── 真实采集 → count(worker 容器内 · default 库)──"
docker exec midas-worker python - <<'PY'
import asyncio
from tasks.crypto_metrics_ingest import (
    _funding_rate_refresh_async, _open_interest_scan_async,
    _global_overview_refresh_async, _get_ch_client,
)
async def main():
    print("[采集] funding :", await _funding_rate_refresh_async())
    print("[采集] oi      :", await _open_interest_scan_async())
    print("[采集] overview:", await _global_overview_refresh_async())
    ch = await _get_ch_client()
    for t in ("crypto_funding_rate", "crypto_open_interest", "crypto_market_overview"):
        n = (await ch.query("SELECT count() FROM " + t)).result_rows[0][0]
        print(f"[COUNT] {t} = {n}")
    await ch.close()
asyncio.run(main())
PY

echo ""
echo "════ 结论看上面 [COUNT] 三行 ════"
echo "  全 >0 → 数据层真落库 · 之前的 0 是验证脚本连接歧义 · M2-A 收口 / M2-C 可开"
echo "  仍 0  → 采集→入库真有 bug · Claude 回去定位(不许跳过)"
echo ""
echo "还原注入代码(可选):docker restart midas-worker"
echo "清理测试数据(可选 · 只清 3 张新表):"
echo "  docker exec midas-clickhouse clickhouse-client --query 'TRUNCATE TABLE crypto_funding_rate'"
echo "  docker exec midas-clickhouse clickhouse-client --query 'TRUNCATE TABLE crypto_open_interest'"
echo "  docker exec midas-clickhouse clickhouse-client --query 'TRUNCATE TABLE crypto_market_overview'"
