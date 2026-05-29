# Runbook · 磁盘 / Docker 构建缓存运维

> 起因:2026-05-29 生产(阿里云香港 VPS)根分区涨到 **100% 满**,元凶是 Docker build
> 缓存堆到 **45.89GB**。手动 `docker builder prune -af` 清掉后磁盘降到 40%。
> 复盘发现 ADR 0029–0031 当年配的缓存护栏存在"按年龄清理"的设计盲区,本 runbook 记录
> 根治后的护栏现状 + 应急 SOP + 回滚步骤。
>
> 关联:ADR 0029(部署健壮性)、ADR 0031(部署健壮性收尾)、`update.sh`、
> `scripts/disk_alert.sh`、服务器 `/etc/docker/daemon.json`。
> 环境:Docker 29.5.2 · `live-restore=true`(重启 Docker 不停运行容器)。

---

## 1. 缓存护栏设计(根治后现状)

构建缓存上限靠**双层**约束,两层都改成了**按大小硬上限**(与部署频率脱钩):

### ① 部署层(主清 · 走部署链)
`update.sh` 7/7 步,每次部署成功后执行:
```bash
docker builder prune -f --keep-storage 10GB
```
- 按 LRU 把 BuildKit 缓存压到 **10GB**,保留最近的热 cache mount(pnpm store / `.next/cache` / pip,共几百 MB~1GB)→ 不伤下次 build 速度,只砍堆积的旧层。
- 每次部署都生效,失败 `|| warn` 不阻塞部署(健康检查已过,此步纯卫生)。

### ② daemon 层(兜底 · 服务器 `/etc/docker/daemon.json`)
即使 `update.sh` 没跑(比如长期不部署、或手动 build),BuildKit 自身 GC 兜底:
```json
{
  "live-restore": true,
  "builder": {
    "gc": {
      "enabled": true,
      "defaultKeepStorage": "15GB",
      "policy": [
        {"keepStorage": "5GB",  "filter": ["unused-for=48h"]},
        {"keepStorage": "15GB"}
      ]
    }
  }
}
```
- 第 1 条:48h 未用的压到 5GB(激进清旧)。
- **第 2 条【无 filter】:任何缓存总量超 15GB 都催收(硬上限)** —— 这是当年漏掉、本次补上的关键规则。

> 防线效果:deploy-prune 10GB 主清(经常触发)+ daemon GC 15GB 兜底(总量硬顶)+ 满之前 TG 告警(见 §2)。

### 为什么这么设计 —— 当年的盲区(必读,别再踩)
- **当年护栏**:`update.sh` 用 `--filter until=168h`,`daemon.json` policy 唯一规则带 `filter:["unused-for=168h"]` —— **两道都只清"7 天未用"的缓存**。
- **盲区**:ADR 0029/0031 为提速引入的 `--mount=type=cache`(pnpm/`.next`/pip)是**每次 build 都复用的持久缓存,永远"最近用过"(<7 天)** → 两道 7-天-filter 对它**全程空转**。`daemon.json` 写了显式 `policy` 还**覆盖了 BuildKit 默认的兜底催收规则**,导致没有任何"无 filter 的硬上限"在管年轻缓存。
- **触发**:密集部署(#296 / 去重 / 通知 / 小尾巴等一周多次 build)缓存一直年轻 → 20GB 上限形同虚设 → 堆到 43GB 打满磁盘。
- **根治思路**:从"按年龄清(unused-for / until=168h)"改成"按大小硬上限(--keep-storage / 无 filter 的 keepStorage)",与部署频率彻底脱钩。

---

## 2. 磁盘告警(`scripts/disk_alert.sh`)

呼应"监控空白"待办的第一块:满盘**之前**就告警。

### 机制
- 系统 cron 每 15 分钟查根分区使用率,超 **85%** 经统一 Telegram bot 发告警给管理员。
- **去抖**:首次越阈值发一条 + 落标记 `/tmp/midas-disk-alerted`;持续越阈值静默(不刷屏);回落到阈值下发"已恢复"并清标记(下次越阈值再报)。
- **可靠性**:仅 TG 发送成功才落标记(失败下轮重试,不漏告警);取不到 `df` 值时跳过本轮(绝不误报)。

### 配置(服务器侧 · Hans)
1. `/etc/midas/alert.env`(chmod 600,root 拥有):
   ```bash
   TG_BOT_TOKEN=<与线上 bot 同一个 token>     # 取自 /opt/midas/.env
   ADMIN_TG_CHAT_ID=<管理员 chat_id>
   ```
   - 取 `ADMIN_TG_CHAT_ID`:给 bot 发条消息 →
     `curl -s "https://api.telegram.org/bot<token>/getUpdates" | grep -o '"chat":{"id":[0-9-]*'`,
     取数字;或复用已 `/start` 绑定的 chat_id。
2. 试跑验证(临时阈值设低,确认手机收到):
   ```bash
   THRESHOLD=1 ./scripts/disk_alert.sh   # 应收到「磁盘告警」
   ./scripts/disk_alert.sh               # 正常阈值,应「正常」无消息
   ```
3. 挂 cron:
   ```
   */15 * * * *  cd /opt/midas && ./scripts/disk_alert.sh >> /var/log/midas-disk-alert.log 2>&1
   ```

### 为什么用独立 cron,而非 celery beat
磁盘满时 worker / celery 自身可能卡死或起不来,届时 beat 任务也发不出告警("自己都挂了")。
独立的系统 cron + bash + curl 不依赖应用栈,是磁盘故障下最可靠的告警路径。与
`backup_postgres.sh` / `backup_clickhouse.sh` 同一套路(系统 cron + `/etc/midas/*.env`)。

---

## 3. 磁盘应急 SOP(再告警 / 再满了怎么办)

### 第一步 · 诊断(看是不是又是构建缓存)
```bash
df -h /                          # 根分区总量 / 已用 / 可用 %
docker system df                 # 镜像 / 容器 / 卷 / Build Cache 各占多少 ← 重点看 Build Cache
docker buildx du --verbose | tail -30   # 缓存明细(看是 cache mount 还是旧层在堆)
```
- 若 **Build Cache** 是大头(最常见)→ 走下面"安全清理"。
- 若是别的(镜像 / 卷 / 日志)→ 见"各目录占用排查"。

### 第二步 · 安全清理(只清缓存,绝不碰容器/镜像/卷/备份)
```bash
docker builder prune -af         # 清【全部】build 缓存(-a 含未引用,-f 免确认)· 立即回收
# 或温和点(保最近 10GB,与部署护栏同口径):
docker builder prune -f --keep-storage 10GB
```
- `docker builder prune` **只动 build 缓存**,不删运行容器、不删镜像、不删数据卷(postgres/clickhouse/redis 数据安全)、不删 `/var/backups/midas` 备份。
- 清完再 `df -h /` 确认回收。

### 各目录占用排查(若不是构建缓存)
```bash
sudo du -h -d1 /var/lib/docker | sort -h    # docker 内部:overlay2(镜像/容器层) / volumes / buildkit
sudo du -h -d1 /var/log | sort -h           # 系统日志 / 容器 json-file 日志(prod 已配 rotate)
sudo du -h -d1 /var/backups/midas 2>/dev/null   # PG/CH 备份(保留 7 天 · 一般不大)
docker ps -s                                # 各容器读写层大小
```
- 容器日志异常大:prod compose 已配 `json-file` rotate(max-size/max-file),正常不会失控;若失控查对应服务日志量。
- **不要**手动删 `/var/lib/docker/` 下任何文件(会损坏 Docker);一律用 `docker ... prune` 命令。

---

## 4. daemon.json 改动 + 回滚

> ⚠️ `daemon.json` 格式错会导致 **Docker 起不来**。铁律:**先备份 → 改 → 校验 JSON → 再重启**。

### 改动步骤(§1 ② 的 15GB 硬上限)
```bash
# 0. 看清现状
sudo cat /etc/docker/daemon.json

# 1. 备份(带时间戳 · 能回滚)
sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak.$(date +%Y%m%d_%H%M%S)

# 2. 写入新内容(本机 daemon.json 仅 builder + live-restore 两键 → 整覆盖安全;
#    若有其他键如 dns/log-driver,改用 jq 合并、勿整覆盖)
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "live-restore": true,
  "builder": { "gc": {
    "enabled": true,
    "defaultKeepStorage": "15GB",
    "policy": [
      {"keepStorage": "5GB",  "filter": ["unused-for=48h"]},
      {"keepStorage": "15GB"}
    ]
  }}
}
JSON

# 3. ★ 校验 JSON 合法(不合法绝不重启!)
sudo python3 -m json.tool /etc/docker/daemon.json >/dev/null && echo "JSON OK" || echo "非法 · 立刻回滚 · 别重启"

# 4. 重启 Docker(live-restore=true · 运行容器不停)
sudo systemctl restart docker && sleep 5

# 5. 确认生效
docker info | grep -iA5 "Builder"        # GC 配置已加载
docker info | grep -i "live restore"     # = true
docker compose -f /opt/midas/docker/docker-compose.yaml -f /opt/midas/docker/docker-compose.prod.yaml ps
                                          # 6 容器仍 running/healthy
df -h /
```

### 回滚(JSON 非法 / 重启后 Docker 起不来)
```bash
sudo cp /etc/docker/daemon.json.bak.<时间戳> /etc/docker/daemon.json
sudo systemctl restart docker
docker info >/dev/null && echo "已回滚 · Docker 正常"
```
- `live-restore=true` 下,即使 dockerd 控制面短暂不可用,运行容器不受影响(只有几秒钟无法 `docker` 操作)。
- 若 `python3` 不在,可用 `docker run --rm -i alpine sh -c 'cat' < /etc/docker/daemon.json | jq .` 之类校验,或 `jq . /etc/docker/daemon.json`。

---

## 速查(TL;DR)
- **又满了?** → `df -h /` → `docker system df` → `docker builder prune -af` → 复查 `df -h /`。
- **护栏现状**:部署后 prune 到 10GB(update.sh)+ daemon GC 硬顶 15GB(daemon.json)+ 85% TG 告警(disk_alert.sh)。
- **改 daemon.json**:先备份 + `python3 -m json.tool` 校验 + restart(live-restore 不停容器)+ 失败 cp 备份回滚。
- **别做**:不手删 `/var/lib/docker/` 文件;prune 不碰容器/镜像/卷/备份,放心清。
