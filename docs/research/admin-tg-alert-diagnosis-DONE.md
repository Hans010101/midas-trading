# admin TG 告警静默失效 · 诊断 + 防复发加固 · 交付归档(DONE)

- 日期:2026-07-16
- PR:#194(护栏 + runbook)· 性质:普通改动(诊断 + 文档 + 启动护栏 · 不碰红线/生产逻辑)
- 触发:Hans 手动触发种子枯竭告警(`celery ... call ... --args='[12]'`)入队成功但 TG 没收到。

## 一句话根因

**`ADMIN_TG_CHAT_ID` 从未配置**(app 侧 `.env` · 默认空)。它是 celery admin 告警线
(种子枯竭 `seed_depletion` / 磁盘 `system_health` / X 熔断 `x_auto`)的**统一发送目标**,
与「日常行情推送」用的 **per-user `notification_config.tg_chat_id`** 是**两套东西**——
所以行情到、告警不到,且**三条 admin 告警集体静默失效**(磁盘一直没到 85% 阈值所以没暴露,
种子告警手动测试才把这个潜伏配置缺口顶出来)。

## 诊断链条(代码坐实 · 无 SSH 全靠代码分析)

1. **两个 chat_id 分属两套**:`dispatcher.py` 行情推送用 `config.tg_chat_id`(用户 /start 绑定);
   `seed_alert.py` / `system_health` / `x_marketing.auto_publish` 熔断都用
   `settings.admin_tg_chat_id`(env `ADMIN_TG_CHAT_ID`,默认 `""`)。收到行情 ≠ admin 配了。
2. **空值静默跳过**:`maybe_alert` 首行 `if not tg_bot_token or not admin_tg_chat_id:
   logger.warning("...admin TG 未配置"); return False`——★`return` 在 `redis.set` 去抖【之前】,
   故空值时连去抖键都不写(反证:没发过)。tg_bot_token 有(行情用它)→ 卡在 admin_tg_chat_id 空。
3. **排除其他**:阈值(celery 5.4 `call --args='[12]'` 正常传入)/ 去抖(键为空 · beat 未到点)/
   任务报错(DB/redis 与 refresh_daily 同 env 正常)——都不是元凶。

## 交付:两件运维加固(PR #194)

### 1. ADMIN_TG_CHAT_ID 防复发
- **启动护栏**:`apps/worker/celery_app.py` `worker_ready` 钩子——`settings.admin_tg_chat_id`
  为空即打显著 WARNING「admin 告警(种子枯竭/磁盘/X 熔断)全部静默失效」。纯 `logger.warning`·
  不 raise · 不阻断既有 `ensure_ch`/入队。防换环境/重装又漏配静默复发。
- **部署前置清单**:`docs/deployment-prerequisites.md` §7 补 `TG_BOT_TOKEN` + `ADMIN_TG_CHAT_ID`
  两行,标注「app 侧 `/opt/midas/.env` 必配 · 空则三告警静默」+「与 `disk_alert.sh` 用的
  `/etc/midas/alert.env` 那个 `ADMIN_TG_CHAT_ID` 是**两处独立**配置,别只配一处」。

### 2. 磁盘 Stage B runbook(`docs/runbooks/disk-and-cache.md` §5)
CH 系统日志瘦身完整命令序列:现状确认(只读)→ recreate CH 加载 `config.d/`(update.sh 同款
COMPOSE · 永不碰 CH)→ DROP 6 张 `remove="1"` debug 表(text_log/trace_log/
processors_profile_log/metric_log/asynchronous_metric_log/query_thread_log)→ 存量
query_log/part_log 补 7 天 TTL(`ALTER`,config `<ttl>` 只对新建表生效 · 易漏)→ 验证 + df。
含影响面(窗口 15-30s~5min / 依赖 CH 功能自愈 / api-worker 不连带重启)+ 不丢数据说明
(业务数据在命名卷 `clickhouse_data`,DROP 的只是 CH 自身 debug 日志)。作为「手动 recreate
长驻容器加载新配置」的通用模板。

## 部署三件套证据(2026-07-16)

1. **Actions 绿**:deploy run 29469380101(merge 3fa70a7)success。★注:#194 CI 首轮
   push+PR 双触发,一次全绿(6m3s)、一次并发争抢 service 容器 hang 到 30m 超时被取消
   (cancelled · 非代码失败,my worker-only 改动不碰 api pytest)· 重跑无并发兄弟即全绿——
   坐实是并发基建 flake。
2. **容器真重建**(部署日志 03:44 UTC):`api / worker 全 Recreated`,
   `✓ force-recreate 完成:api worker`,HEAD=3fa70a7 · 0 条 "Running upgrade"
   (纯代码+文档无迁移,符合)· worker 重建 = 加载新 `worker_ready` 护栏。
3. **护栏活性(★现网自证)**:因当前 `ADMIN_TG_CHAT_ID` 仍空,worker 启动日志现在**必打**
   那条 WARNING —— 既验证护栏生效,又**再次坐实根因**(该变量确未配)。Hans 可查:
   `docker logs midas-worker 2>&1 | grep "ADMIN_TG_CHAT_ID 未配置"`。

## ★真正修好告警 = Hans 一步手动(PR 补不了服务器 secret)

服务器 `/opt/midas/.env` 加 `ADMIN_TG_CHAT_ID=<你的 TG 数字 chat_id>`(复用 `/start` 已绑的,
或跟 bot 私聊用 @userinfobot 读数字)→ 重建 worker+api。配上后:
1. 三条 admin 告警(含种子枯竭)才真正生效;worker 启动那条 WARNING 消失(= 配对了的信号)。
2. 重跑 `celery ... call ... --args='[12]'` 应收到 6 条种子告警(cn_cpi/ppi/gdp/boj/bok/gb_boe;
   ECB 17 月不触发)· 去抖 7 天(重测先清 `monitor:seed_depletion:sent:*`)。
3. **附带**:磁盘 `system_health` 告警 + X 熔断告警也一起活(仨共用这根线)。

## 自验

`celery_app` 干净 import(PYTHONPATH=api:worker + 空 `ADMIN_TG_CHAT_ID`)· guard 空值分支
可达(WARNING 真打)· runbook DROP 表名/保留表逐一对齐 `docker/clickhouse-logs.xml`
(6 张 remove + query_log/part_log 保留 TTL)。纯 worker 侧代码 + 文档,不碰 apps/api,CI api 闸不受影响。
