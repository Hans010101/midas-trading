# 港股接入 · 阶段零实测脚本(ADR 0034)

**两个只读探测脚本** · 给 Hans 在服务器跑 · 实测结果回来定:主源(决策①)/ CH 迁移可行性 / 每手字段有无(决策②)。

> ★ 两个脚本**都只读**:零-A 只对 ClickHouse 发 SELECT/SHOW;零-B/C 只拉上游行情(akshare/yfinance)。
> **绝不改任何库、不写数据、不动配置、不执行 ALTER**。

---

## 零-A · CH Enum8 迁移探测(`probe_ch_enum8.sh`)
**在服务器宿主机跑**(需 docker 权限 + CH 密码):
```bash
cd <仓库目录>
git fetch && git checkout feat/hk-phase0-probes      # 或拉到本脚本所在分支
CLICKHOUSE_PASSWORD='<服务器 .env 里的 CLICKHOUSE_PASSWORD>' \
  bash scripts/hk-phase0/probe_ch_enum8.sh
```
- 可选覆盖:`CH_CONTAINER`(默认 `midas-clickhouse`)`CH_DB`(默认 `default`)`CH_USER`(默认 `midas`)。
- **看什么输出**:① kline/symbol_meta 的 `market Enum8` 定义 ② 数据量 + 分区分布 ③ 现有 market 取值
  ④ 脚本末尾的「metadata-only 评估」+ 阶段一将执行的 ALTER/回滚语句(**脚本不执行,只 echo 给你审**)。
- 回贴全部输出 → 我们判断 ALTER 加 `'hk'=4` 是否能秒级 metadata-only 平滑迁移。

## 零-B/C · 港股数据源探测(`probe_hk_data.py`)
**在 api 容器里跑**(容器已装 akshare/yfinance · 从宿主机管道喂入,不必拷进镜像):
```bash
docker exec -i midas-api python - < scripts/hk-phase0/probe_hk_data.py
```
（容器名若不是 `midas-api`,换成实际名;脚本走 stdin,不依赖脚本在镜像内。）
- **看什么输出**:
  · akshare 港股函数清单 + `stock_hk_hist`(00700)历史 K 线字段/复权
  · akshare `stock_hk_spot_em` 实时快照列 + **★ 有没有「每手」字段**(零-C)
  · yfinance `0700.HK` history + info(币种/最新价/**延迟分钟数**/lot 键)
  · 末尾「结论模板」——人工据输出填:主源选谁、延迟多少、每手字段有无。

---

## 实测通过判定(回 ADR 0034 阶段零)
- 零-A:ALTER 可 metadata-only 平滑(or 有可控迁移方案)。
- 零-B:0700.HK 历史/实时/复权可用,延迟 ≤ ~15min,akshare 或 yfinance 至少一个质量过关 → 定主源。
- 零-C:每手字段有(直接采)or 无(决策②手动策展兜底,已认可)。
- 三项绿 → 进阶段一写代码;任一卡死 → 回产品负责人重定方案。

## 红线
- 两脚本只读;真正的 CH `ALTER MODIFY … 'hk'=4`(+ 回滚)在**阶段一**做、低峰 + 停 worker(决策⑤)。
- CH 密码只从服务器 env 取,**不写进脚本、不提交**。
