#!/bin/bash
# 点金 Midas · M2-A 真实核查 v2 · 隔离测试库 · 一锤定音
#
# 跑法(一行 · git 把脚本写到 /tmp 再执行):
#   cd /opt/midas && git fetch origin feature/m2-crypto-pro && \
#     git show origin/feature/m2-crypto-pro:scripts/m2a-realcheck.sh > /tmp/m2a-realcheck.sh && \
#     bash /tmp/m2a-realcheck.sh 2>&1 | tee /tmp/m2a-realcheck.log
#
# 消歧义 + 零污染:
#   · 采集入口内部用 _get_ch_client(database=settings.clickhouse_database)
#   · 经 `docker exec -e CLICKHOUSE_DATABASE=m2_verify_check` 重定向到测试库
#     → 采集 client 和 count client 同一个、同一个测试库,彻底没"写A库读B库"歧义
#   · 生产 default 库:零写入、零建表、一个表都不碰
#   · 测试库 m2_verify_check 用完 DROP(测试库 DROP 安全)
#
# 边界:docker exec 进现成 midas-worker(不临时容器/不 worktree)· 不调 update.sh ·
#       注入的 feature 代码靠 `docker restart midas-worker` 还原(测试库另行 DROP)。

set -e
DB=m2_verify_check
cd /opt/midas
git fetch --force origin "+refs/heads/feature/m2-crypto-pro:refs/remotes/origin/feature/m2-crypto-pro"
T=$(git rev-parse refs/remotes/origin/feature/m2-crypto-pro)
echo "════ feature commit: $T ════"; git log --oneline -1 "$T"

# 1. 把 feature 的 worker/api 代码注入运行中的 worker(覆盖 /repo/apps · 只改文件 · docker restart 还原)
echo "── 注入 feature 代码到 midas-worker ──"
git archive "$T" apps/api apps/worker | docker exec -i midas-worker tar -x -C /repo
echo "  done"

# 2. 在【测试库 m2_verify_check】建 3 张待查表(不是 default · 用完会 DROP)
echo "── 测试库 $DB 建 3 张 crypto 表(生产 default 不碰)──"
docker exec midas-clickhouse clickhouse-client --query "CREATE DATABASE IF NOT EXISTS $DB"
docker exec -i midas-clickhouse clickhouse-client --database "$DB" --multiquery <<'SQL'
CREATE TABLE IF NOT EXISTS crypto_funding_rate (symbol String, ts DateTime, rate Float64, mark_price Float64, ingested_at DateTime DEFAULT now()) ENGINE=ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY (symbol, ts);
CREATE TABLE IF NOT EXISTS crypto_open_interest (symbol String, ts DateTime, oi_coin Float64, oi_usd Float64, ingested_at DateTime DEFAULT now()) ENGINE=ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY (symbol, ts);
CREATE TABLE IF NOT EXISTS crypto_market_overview (ts DateTime, total_market_cap_usd Float64, total_volume_24h_usd Float64, btc_dominance Float64, eth_dominance Float64, fear_greed_value UInt8 DEFAULT 0, fear_greed_classification String DEFAULT '', derivatives_oi_usd Float64 DEFAULT 0, derivatives_volume_24h_usd Float64 DEFAULT 0, ingested_at DateTime DEFAULT now()) ENGINE=ReplacingMergeTree(ingested_at) PARTITION BY toYYYYMM(ts) ORDER BY ts;
SQL
echo "  done"

# 3. 真实采集 + count(全程测试库 · -e 在 python 启动前设好 · settings import 时就取它)
echo "── 真实采集 → count(worker 容器内 · 重定向到测试库 $DB)──"
docker exec -e CLICKHOUSE_DATABASE="$DB" midas-worker python - <<'PY'
import asyncio
from app.core.config import settings
# 自证:确认 worker 这次连的是测试库,不是 default
print(f"[自证] settings.clickhouse_database = {settings.clickhouse_database}")
assert settings.clickhouse_database == "m2_verify_check", "未重定向到测试库 · 中止(绝不写 default)"
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

# 4. DROP 测试库(测试库 DROP 安全 · 生产 default 始终没碰)
echo "── DROP 测试库 $DB ──"
docker exec midas-clickhouse clickhouse-client --query "DROP DATABASE IF EXISTS $DB"
echo "  done · 生产 default 库:零写入、零建表、零删除"

echo ""
echo "════ 结论看上面 [COUNT] 三行 ════"
echo "  全 >0 → 数据层真落库(同库同 client · 零歧义)· M2-A 收口 / M2-C 可开"
echo "  仍 0  → 采集→入库真有 bug · Claude 回去定位(不跳过)"
echo ""
echo "还原注入的 feature 代码(可选):docker restart midas-worker"
