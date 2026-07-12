# 硬编码年度种子枯竭告警 · 交付归档(DONE)

- 日期:2026-07-11
- PR:#193 · 调研:docs/research/seed-crossyear-automation-feasibility.md
- 性质:P1 · 纯监控层(非红线级 · CI 兜底 · 不交叉审)

## 交付范围

- [x] `app/services/econ_calendar/seed_alert.py`(逻辑层·可单测):查每个 `source='seed'`
      event_type 的 `max(scheduled_at)`,最远日期 < 3 月 → `telegram.send(admin)` + Redis
      按 event_type 去抖 7 天。复用 system_health 范式,零新依赖。
- [x] `apps/worker/tasks/seed_depletion.py`(薄壳):beat 每日 09:17 CST · PG 引擎+redis →
      run_check · 全 try/except 绝不崩 worker。celery_app 显式 import + celery_config beat 注册。
- [x] 覆盖 5 硬编码种子(中国CPI/PPI/GDP + BOJ/BOK/BoE/ECB 议息 · 共 7 个 event_type);
      抓取/滚动源(fed/bea/kostat/jp_estat/boj_xlsx/dsbb/rule)★排除(DB 测试钉死)。
- [x] ★口径:max(scheduled_at) 合法(问「数组还剩多远到头」),与 ingest_monitor last-run
      新鲜度【正交并存·不干扰】· 绝不用本任务 max(ts) 替换 last-run 判定。
- [x] months_override 参数 = 可控验证手段(手动 call 传大阈值立即触发)。

## 部署三件套证据(2026-07-11)

1. **Actions 绿**:run 29147514912(merge 1d5233e)全 job success
2. **容器真重建**(部署 job 日志 09:26 UTC):`api / worker 全 Recreated`(worker 重建 =
   celery beat 加载新任务)· 无 alembic 变更(0 条 "Running upgrade")
3. **告警链路验证**:
   - 单测(CI 真 PG 绿):`test_maybe_alert_sends_then_debounces`(telegram.send 真被调 +
     文案含种子名 + rules.py 补种位置 + 去抖首发/二次不重发)· `test_run_check_end_to_end`
     (DB→筛快枯竭→告警,近期触发/远期不触发)· `test_seed_max_dates_only_seeds_not_rolling`
     (只种子非滚动源)· 纯逻辑 5 + DB 2 全过
   - ★现网:最近枯竭 cn_gdp(2026-10-19,~3.3 月)→ 约 **2026-07-21 起自然告警**

## Hans 可控验证(想立刻看 TG 告警)

服务器一条命令,传大阈值(如 12 月)让当前所有种子立即触发,确认 admin TG 收到:
```
docker exec midas-worker celery -A celery_app call tasks.monitor.check_seed_depletion --args='[12]'
```
- 首次会给每个种子发一条 TG(7 条:cn_cpi/ppi/gdp/boj/bok/gb_boe/ecb),文案含最远日期 +
  该补 rules.py 哪个数组。
- ★去抖 7 天:想重测请先清 Redis 键 `docker exec midas-redis redis-cli --scan --pattern
  'monitor:seed_depletion:sent:*' | xargs -r docker exec -i midas-redis redis-cli del`(或等 7 天)。
- 默认 beat(不传参)用 3 月阈值,当前只有 cn_gdp 临近(7/21 起)。

## 已知边界 / 后续

- 阈值 3 月(硬编码常量);各央行发布节奏不同但统一 3 月够(种子提前量大多 ≥半年)。
- 迁源(消除硬编码)是独立 P2:中国 CPI/GDP 可迁 DSBB(碰决策卡注入·红线级需单独一刀);
  BOJ/BOK/BoE 议息实测无零成本机读源,认命硬编码 + 本告警兜底(见调研 doc)。
