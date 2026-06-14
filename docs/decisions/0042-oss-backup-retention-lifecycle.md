# ADR 0042 · OSS 备份保留改由桶生命周期规则管理(移除脚本侧 ossutil rm -b 删除逻辑)

- 状态:**Accepted**(产品负责人指令 · 2026-06-14)
- 日期:2026-06-14
- 相关:0006(部署 · PG 备份起源)· scripts/backup_postgres.sh · scripts/backup_clickhouse.sh ·
  桶 `midas-backup-hk`(已配生命周期规则:prefix `clickhouse/` 保留 7 天 · prefix `postgres/` 保留 30 天 · 均 active)

## 背景

两个备份脚本(PG / ClickHouse)上传 OSS 后,各带一段「清 OSS 上 RETAIN_DAYS 天前旧备份」的 **fallback**:
`ossutil ls` 列对象 → `awk`/`grep` 算出过期 key → `while` 逐个 `ossutil rm "$key" ... -f -b`。

### Bug 根因(实证)

`-b`(`--bucket`)是**删整个桶**的开关。拿它删单个对象,ossutil 每天必报错并退出:

```
Error: remove bucket invalid url: ...
object not empty, if you mean remove object, you should not use --bucket option
```

→ **OSS 上的过期备份从来没被删掉过,只增不减**。脚本自己的注释也写明「OSS 用 lifecycle rule 更稳,这里只做 fallback」——
这个 fallback 不仅无效,还是错的(`-b` 是危险开关,语义是删桶)。本地 `find -delete` 清理一直正常,所以本地暂存没堆积,
问题只在 OSS 侧静默累积。

## 决策

**OSS 端保留改由平台桶生命周期规则(bucket lifecycle)接管,脚本不再删 OSS。**

- 桶 `midas-backup-hk` 已配两条生命周期规则(已 active):
  - prefix `clickhouse/` → 保留 **7 天**
  - prefix `postgres/` → 保留 **30 天**
- 两个脚本删除各自的「清 OSS 旧备份」整段(注释 → `CUTOFF_DATE` → `ossutil ls | awk | grep | while ... ossutil rm ... -f -b ... done`,
  ClickHouse 版连同外层 `{ ... } || true` 包裹一并删),原位替成一行注释:
  `# OSS 端保留由桶生命周期规则负责(clickhouse/ 7d、postgres/ 30d);脚本不再删 OSS。`
- 脚本头注释同步:`RETAIN_DAYS` 口径收窄为**仅管【本地暂存】清理**;OSS 保留由桶生命周期负责(CH 7 天 / PG 30 天)。

为什么交给平台:① 生命周期规则是 OSS 原生能力,服务端按 prefix + 天数自动过期,无客户端逻辑、无凭证、无 cron 失败面;
② 脚本侧删除既已证明是错的(`-b`),修它不如撤掉——少一段会动数据的危险代码,符合「最小动数据」原则。

## 影响

- 两个脚本**只保留本地** `find "$BACKUP_DIR" -name ... -mtime "+${RETAIN_DAYS}" -delete` 清理;**不再删 OSS**。
- pg_dump / ClickHouse 逐表导出(Native+gzip)/ manifest / trap 清理 / 上传(`ossutil cp`)/ 大小校验 / 恢复 runbook **全部不变**。
- OSS 过期清理改由桶生命周期静默执行——CH 备份 7 天后、PG 备份 30 天后由平台自动删,脚本不再产生 ossutil rm 报错。
- 保留天数口径分离:`RETAIN_DAYS`(默认 7)= 本地暂存窗口;OSS 保留 = 桶规则(CH 7 / PG 30),两者独立,改一个不影响另一个。
- 凭证仍走 `/etc/midas/backup.env`(chmod 600),脚本不写入代码 / 不进日志,本次改动不碰凭证面。

## 验证 / 部署

- 提交前:`shellcheck` 两脚本 = 0(无告警)· `bash -n` 两脚本 = 0(无语法错)。
- 仅改 `scripts/` + 新增本 ADR(`docs/`),不碰 `apps/api/**` / `apps/web/**` →
  `test.yml` / `web-test.yml` 的 paths 过滤器不触发(预期 · 无需新增测试 / workflow)。
- 合 main 触发 `deploy.yml` → `update.sh` 的 `git reset --hard origin/main` 把新脚本同步到服务器 `/opt/midas/scripts`;
  脚本改动**无需重建容器**,下一次 cron 即用新脚本。
