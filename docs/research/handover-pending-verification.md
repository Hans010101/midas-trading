# 交接材料「待确认项」只读核查报告(P2-prep 任务4 · 2026-06-10)

> 范围:OSS 备份是否在跑 / cn-preview·us-preview 实际内容 / 监控告警聚合现状。
> 方法:纯代码仓只读核查;代码能定的给结论,要连生产的标注「待 Hans Workbench 实证」+ 备好命令。

## 1. OSS 备份(midas-backup-hk)

**代码层确认(实证):脚本存在且设计完整,但「是否真在跑」代码定不了。**

| 脚本 | 仓库状态 | 设计 |
|---|---|---|
| `scripts/backup_postgres.sh` | ✅ 在库(0006/部署 ADR · 2026-05-21) | 每日 pg_dump → `oss://midas-backup-hk/postgres/` · 保留 7 天 · 凭证 `/etc/midas/backup.env`(chmod 600)· cron 建议 `0 3 * * *` → `/var/log/midas-backup.log` |
| `scripts/backup_clickhouse.sh` | ✅ 在库(2026-05-29 · 与 PG 同构) | 全量 *MergeTree 表(动态枚举)→ `oss://midas-backup-hk/clickhouse/` · ★头注释明示「**Hans 手动试跑验证通过后再挂 cron**(03:30 错峰)」→ **是否已挂 cron 未知** |
| `scripts/disk_alert.sh` | ✅ 在库 | 磁盘告警(85% 告警可能即出自此) |
| `disk-cleanup.sh` | ❌ **不在仓库**(scripts/ 无此文件) | 任务卡称已上线 `/opt/midas/scripts/disk-cleanup.sh` + cron 4 点 → **服务器侧手工脚本 = 配置漂移风险**,建议入库纳管(Hans 拍;入库后 update.sh 同步即治) |

**★ 顺带重要发现**:`backup_clickhouse.sh` 头注释 2026-05-29 摸底「default 库全部 MergeTree 表**整库约 151 MiB**」——与交接材料「CH 已是 32G」口径相差两个数量级。**32G 大头疑似不在业务表**(嫌疑:ClickHouse system 日志表 query_log/trace_log/metric_log 无 TTL 累积、或卷内其他内容)。这直接改变 K2b 的磁盘账与优先级 → 已写进 ADR 0039 让 Hans 一并实证。

**待 Hans Workbench 实证(整段复制):**
```bash
# ① 备份/清理 cron 是否真挂着
crontab -l | grep -iE 'backup|cleanup|disk' || echo "(root crontab 无备份/清理条目)"
# ② 备份日志最近几条(在跑则每天有新行)
tail -5 /var/log/midas-backup.log 2>/dev/null || echo "(无 midas-backup.log → PG 备份 cron 可能没挂)"
tail -5 /var/log/midas-cleanup.log 2>/dev/null || echo "(无 midas-cleanup.log)"
# ③ 服务器侧 scripts 与仓库的漂移(disk-cleanup.sh 应只在服务器)
ls -la /opt/midas/scripts/
```

## 2. cn-preview / us-preview 实际内容(实证 · 代码层可定)

两页均为**薄 Suspense 壳包共享 `SpotDetail`**(与 crypto-preview 同构,0023 阶段③ 3.4 批2):
- `app/cn-preview/page.tsx` → `<SpotDetail market="cn" />`(?symbol=600519)
- `app/us-preview/page.tsx` → `<SpotDetail market="us" />`(?symbol=NVDA;右栏下单区支持做多+**虚拟卖空**——负持仓记账,无杠杆)
- 共同点:middleware 不保护(匿名可看 K线/缠论/AI),下单时组件内引导登录;头注释红线齐全(永远虚拟资金)。
- **结论:内容正常、与 crypto/hk 详情页同构,无待办暗坑。**

## 3. 监控告警聚合现状(实证 · 代码层可定)

全仓 grep `sentry|datadog|prometheus|grafana|uptime|pagerduty` = **0 命中** → **无聚合监控/APM/错误追踪**。现状拼图:
- 部署时一次性健康检查(deploy.yml「外部健康检查 · 公网 HTTPS 端点」——只在部署那一刻);
- `scripts/disk_alert.sh`(磁盘单项);
- 业务通知系统(TG/飞书 → 用户侧行情/订单通知,非系统监控)。

**改进候选(仅列出,不行动,Hans 排期)**:① 最小可用 = 外部 uptime 探针(UptimeRobot 免费档)打 `/health` + TG 通知;② 容器维度 = `docker events`/healthcheck 状态推 TG 的轻量 cron;③ 重一点 = self-host Uptime-Kuma(再 +1 常驻容器,内存账要算)。

## 4. 汇总

| 项 | 代码层结论 | 还差什么 |
|---|---|---|
| PG 备份 | 脚本✅设计完整 | cron+日志 待 Workbench 实证 |
| CH 备份 | 脚本✅(头注释:试跑后才挂 cron) | 是否已挂 待实证 |
| disk-cleanup.sh | **不在仓库**(漂移) | 建议入库纳管(Hans 拍) |
| cn/us-preview | ✅ 同构 SpotDetail · 无暗坑 | 无 |
| 监控聚合 | **无**(仅部署时检查+磁盘脚本) | 改进候选已列,Hans 排期 |
