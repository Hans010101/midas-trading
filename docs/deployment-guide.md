# 点金 Midas · 部署指南(M1 第三波)

**产品负责人 2026-05-21 决策:** 前端 Vercel + 后端阿里云香港 VPS · 香港不备案 · 每日 pg_dump → 阿里云 OSS 香港。

> **2026-05-21 更新:** 服务器已就位 · IP `8.210.156.91` · 域名 `midastrade.asia` · Ubuntu 24.04 · 4 vCPU / 8GB。
>
> **三份文档分工:**
> - **本文档** · 架构 + 设计决策(读一次知全貌)
> - [`deployment-prerequisites.md`](deployment-prerequisites.md) · 凭证清单(产品负责人按这个准备)
> - [`deployment-runbook.md`](deployment-runbook.md) · 17 步执行手册(实际部署照这个跑)

---

## 1 · 部署架构

```
┌────────────────────────────┐         ┌─────────────────────────────┐
│  浏览器 / App               │ HTTPS  │   Vercel(静态官网 + Next.js) │
│  midastrade.asia    │ ←────→ │   midas-web.vercel.app       │
└────────────────────────────┘         └─────────────────────────────┘
                                                  │ SSR / API 反代
                                                  ↓
                                       ┌─────────────────────────────┐
                                       │   阿里云 香港 VPS(单台)     │
                                       │   Caddy(HTTPS 反代 + LE)    │
                                       │     ↓                       │
                                       │   docker compose:           │
                                       │     - midas-api  :8000      │
                                       │     - midas-worker          │
                                       │     - midas-postgres        │
                                       │     - midas-clickhouse      │
                                       │     - midas-redis           │
                                       └─────────────────────────────┘
                                                  │
                                                  ↓ 每日 03:00 UTC
                                       ┌─────────────────────────────┐
                                       │ 阿里云 OSS(香港 region)     │
                                       │ midas-backup-hk             │
                                       │   postgres/midas-pg-*.sql.gz │
                                       │   保留 7 天                  │
                                       └─────────────────────────────┘
```

**为什么这个拓扑:**
- 前端 Vercel:免费 + 全球 CDN + Next.js 原生 · 0 运维负担
- 后端阿里云香港:不备案 + 国内访问延迟低(< 100ms)+ 内网到 OSS 免流量费
- Caddy 反代:Let's Encrypt 全自动 HTTPS · 比 Nginx 配置少一半
- 单 VPS 起步:百用户级别 4 core/8GB 足够 · 后续按需拆 ECS

---

## 2 · 生产 .env 必须替换的项

**当前 `/Users/hans.pan/点金Midas/.env` 在本机 dev 跑得动 · 但有 2 项生产必换。**

### 2.1 `SECRET_KEY`(生产必换)

**当前:** `SECRET_KEY=REPLACE_ME`(本机 dev 能跑只因为 Settings 接受任意字符串)

**生产生成强密钥:**
```bash
openssl rand -hex 32
# → 类似 a1b2c3...d4e5f6 64 字符
```

**关键:** 这个 key 控制 NextAuth cookie 签名 + 任何 HMAC 用途。**生产泄露 = 全量用户被假冒。**

### 2.2 `DEEPSEEK_API_KEY`

已经填好(M1 二波验收)· 生产用同一个 key OR 申请单独的生产 key(避免 dev/prod 配额混淆)。

### 2.3 其他生产必填(本机 dev 可空)

| 变量 | 生产值 | 备注 |
|---|---|---|
| `RESEND_API_KEY` | 真实 key | 邮箱验证用 · 0006 ADR |
| `EMAIL_FROM` | `noreply@midastrade.asia` | 必须配 DNS SPF · 否则进垃圾箱 |
| `PUBLIC_WEB_URL` | `https://midastrade.asia` | 邮件验证链接 base URL |
| `NEXT_PUBLIC_API_URL` | `https://api.midastrade.asia` | 浏览器侧 API URL |
| `API_INTERNAL_URL` | 不需要(Vercel 走公网)| 或后端反代域名 |
| `AUTH_TRUST_HOST` | `"true"` | NextAuth v5 在容器后 必备 |
| `AUTH_SECRET` | 跟 SECRET_KEY 同一个值 | NextAuth v5 重命名了 |
| `CORS_ORIGINS` | `["https://midastrade.asia"]` | 严格匹配 · 不要 `*` |

### 2.4 备份凭证(放在 VPS 上 `/etc/midas/backup.env`)

```bash
# chmod 600 /etc/midas/backup.env · root 拥有
OSS_ENDPOINT=oss-cn-hongkong-internal.aliyuncs.com
OSS_BUCKET=midas-backup-hk
OSS_ACCESS_KEY_ID=LTAI...
OSS_ACCESS_KEY_SECRET=...
```

**关键:** 用 `oss-cn-hongkong-internal` 内网 endpoint · VPS 跟 OSS 在同 region 时走免费内网流量。

---

## 3 · 阿里云香港 VPS 从零部署

### 3.1 准备工作(产品负责人)

| 步骤 | 内容 | 估时 |
|---|---|---|
| ① | 阿里云轻量 香港 · 4 vCPU / 8GB RAM / 70GB SSD · Ubuntu 24.04 ✅ 已就位 | — |
| ② | 阿里云开 OSS bucket(香港 region)· 名称 `midas-backup-hk` | 3 min |
| ③ | 阿里云 RAM 子账号 + AccessKey · 只授权 `oss:PutObject` / `oss:ListObjects` / `oss:DeleteObject` on `midas-backup-hk` | 5 min |
| ④ | 域名解析:`api.<domain>` A 记录指向 VPS 公网 IP | 5 min |
| ⑤ | 域名解析:`app.<domain>` CNAME 指向 Vercel 提供的 DNS 名 | 5 min |
| ⑥ | 安全组开放端口:80 / 443(给 Caddy)· 22(SSH)· 不开 5432 / 6379 / 8123 / 8000 | 3 min |

### 3.2 VPS 初始化(SSH 登录后跑)

```bash
# 系统更新
sudo apt update && sudo apt upgrade -y

# 装 Docker + Compose plugin
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER
# 重新登录 SSH 让 group 生效

# 装 Caddy(自动 HTTPS · Let's Encrypt)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy

# 装 ossutil(阿里云 OSS CLI)
wget https://gosspublic.alicdn.com/ossutil/1.7.18/ossutil64
chmod +x ossutil64
sudo mv ossutil64 /usr/local/bin/ossutil
```

### 3.3 拉代码 + 配置

```bash
sudo mkdir -p /opt/midas
sudo chown $USER:$USER /opt/midas
cd /opt/midas
git clone https://github.com/your-github-username/midas.git .

# 复制 .env 模板 · 改成生产值(详见 § 2)
cp .env.example .env
nano .env
# 至少改:SECRET_KEY / DEEPSEEK_API_KEY / RESEND_API_KEY /
#   PUBLIC_WEB_URL / NEXT_PUBLIC_API_URL / CORS_ORIGINS /
#   POSTGRES_PASSWORD

# 备份凭证(单独路径 · 权限 600)
sudo mkdir -p /etc/midas
sudo nano /etc/midas/backup.env       # 粘贴 § 2.4 内容
sudo chmod 600 /etc/midas/backup.env
sudo chown root:root /etc/midas/backup.env
```

### 3.4 启动 docker compose(生产 overlay)

```bash
cd /opt/midas
docker compose \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.prod.yaml \
  up -d
```

**自验:**
```bash
docker compose ps                # 全部 healthy
curl -s http://127.0.0.1:8000/health   # → {"status":"ok"}
```

### 3.5 跑 alembic migration

```bash
docker exec midas-api alembic upgrade head
```

### 3.6 Caddy 反代配置(`/etc/caddy/Caddyfile`)

```caddyfile
# 后端 API 反代
api.midastrade.asia {
    reverse_proxy 127.0.0.1:8000
    encode gzip

    # 上游 4xx/5xx 直接透传 · 不要 Caddy 自己包错误页
    handle_errors {
        respond "Upstream error: {http.error.status_code}" {http.error.status_code}
    }
}

# 如果选择 self-hosted Web(不走 Vercel)
# midastrade.asia {
#     reverse_proxy 127.0.0.1:3000
#     encode gzip
# }
```

```bash
sudo systemctl reload caddy
# Caddy 自动申请 LE 证书 · 几秒钟搞定
curl https://api.midastrade.asia/health   # → {"status":"ok"}
```

### 3.7 配 cron · 每日 3 点备份

```bash
# 用 hans 用户的 crontab(脚本不需要 root · 但读 /etc/midas/backup.env 需要 root)
sudo crontab -e
# 加这一行:
0 3 * * *  cd /opt/midas && /opt/midas/scripts/backup_postgres.sh >> /var/log/midas-backup.log 2>&1
```

**首次手动跑一次验证:**
```bash
sudo /opt/midas/scripts/backup_postgres.sh
# 期望输出:
#   [backup] start
#   [backup] dump OK · 1.2M
#   [backup] uploaded → oss://midas-backup-hk/postgres/midas-pg-...sql.gz
#   [backup] local cleanup
#   [backup] OSS expire(首次没文件可清)
#   [backup] done
```

**OSS lifecycle rule(推荐 · 替代脚本里的 OSS 清理逻辑):**
- 阿里云控制台 → midas-backup-hk → 基础设置 → 生命周期
- 规则:前缀 `postgres/`,7 天后自动删除
- 脚本里的 OSS 删除作为 fallback · 一般用不到

---

## 4 · Vercel 前端部署

### 4.1 准备

| 步骤 | 内容 |
|---|---|
| ① | Vercel 账号(产品负责人已确认) |
| ② | GitHub repo 公开 / Vercel 拿到访问权限 |
| ③ | DNS:`midastrade.asia` CNAME → `<vercel-project>.vercel.app`(Vercel 引导时给) |

### 4.2 创建 Vercel 项目

1. Vercel 后台 → New Project → Import Git repo
2. **Root Directory:** `apps/web`
3. **Framework Preset:** Next.js(自动检测)
4. **Build Command:** `cd ../.. && pnpm install --frozen-lockfile && pnpm --filter @midas/web build`
5. **Output Directory:** `apps/web/.next`(默认)
6. **Install Command:** `pnpm install`

### 4.3 Vercel 环境变量

| Key | Value | 备注 |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.midastrade.asia` | 浏览器调后端 |
| `API_INTERNAL_URL` | `https://api.midastrade.asia` | Vercel SSR 调后端(Vercel 不在 VPS 同内网,只能走公网域名)|
| `AUTH_SECRET` | 跟 VPS 的 SECRET_KEY 一致 | NextAuth cookie 签名 |
| `AUTH_TRUST_HOST` | `true` | Vercel 在反代后必备 |

### 4.4 自定义域名

Vercel → 项目设置 → Domains → 添加 `midastrade.asia` · 按 Vercel 指引在 DNS 加 CNAME。

### 4.5 部署后自验

```bash
curl https://midastrade.asia/                # Vercel 首页
curl https://midastrade.asia/workbench       # /workbench 匿名可访问(M1-B)
curl https://api.midastrade.asia/health          # 后端 healthy
```

注册流程:打开 `https://midastrade.asia/register` → 真实邮箱 → 收 Resend 邮件 → 验证 → 登录。

---

## 5 · 灾难恢复(从 OSS 恢复 DB)

### 5.1 列出可用备份

```bash
ossutil ls oss://midas-backup-hk/postgres/ -s
```

### 5.2 下载 + 恢复

```bash
# 1. 下载
ossutil cp oss://midas-backup-hk/postgres/midas-pg-20260521T030000Z.sql.gz /tmp/

# 2. 停 api / worker(避免 query in 进行中)
cd /opt/midas
docker compose stop api worker

# 3. drop + recreate database(谨慎!)
docker exec -it midas-postgres psql -U midas -d postgres -c "DROP DATABASE midas;"
docker exec -it midas-postgres psql -U midas -d postgres -c "CREATE DATABASE midas;"

# 4. 灌入备份
gunzip -c /tmp/midas-pg-20260521T030000Z.sql.gz | \
  docker exec -i midas-postgres psql -U midas -d midas

# 5. 跑 migration(确认 schema 版本)
docker exec midas-api alembic upgrade head

# 6. 启动
docker compose start api worker
```

### 5.3 验证恢复

```bash
docker exec midas-postgres psql -U midas -d midas -c "SELECT COUNT(*) FROM \"user\";"
# 检查用户数跟备份时刻一致
```

---

## 6 · 不在本指南范围(后续 ADR)

- **HTTPS 证书自动续期监控** · Caddy 自动续 · 但建议加 Uptime Robot 监 cert expiry
- **OSS 跨区备份(灾备)** · 香港 region 万一挂了 · M2+ 考虑加新加坡 / 美国 cross-region replication
- **应用日志聚合** · 当前 docker json-file driver 落本地 · M2+ 接 Loki / Grafana Cloud
- **Prometheus 监控** · M2+(0012 ADR 监控章节已规划)
- **CDN 静态资源** · Vercel 自带 · 不需要额外配
- **WAF / DDoS 防护** · 阿里云 ECS 自带基础 · M2+ 评估上 WAF
- **Vercel 团队定价** · 免费档单项目够 · 用户超 100 个 / 月或带宽超 100GB 时升级 Pro($20/月)

---

## 7 · 备份脚本本地测试(开工部署前)

部署前在 dev 环境测一次脚本可跑:

```bash
# 假凭证 + 假 bucket · 跑前两步(pg_dump + 本地文件)· 不真传 OSS
cd /Users/hans.pan/点金Midas
# 改一下脚本临时跳过 ossutil 那段,或者用 minio + ossutil-compatible client 跑全流程
# (M1 三波不强制 · 真部署时用真凭证跑一遍即可)
```

---

## 8 · 部署后自检 checklist

部署完成后跑一遍:

- [ ] `curl https://api.midastrade.asia/health` → 200 OK
- [ ] `curl https://midastrade.asia/` → Vercel 首页(M1 后续视觉)
- [ ] `https://midastrade.asia/workbench` → 匿名可看 K 线(M1-B)
- [ ] 点 watchlist「添加」/ 顶部「买入」→ 跳 /login(M1-B)
- [ ] 注册 → 收 Resend 邮件 → 点链接 → /workbench(完整链路)
- [ ] 登录后 /workbench/sell 触发下单 → 200(M1-A session 工作)
- [ ] /api/v1/analysis/decision-card → `llm_mode: 'real'`(M1 二波)
- [ ] 手动 `./scripts/backup_postgres.sh` → 看到 `oss://midas-backup-hk/postgres/...` 文件
- [ ] cron 设好 · `sudo crontab -l` 含每日 03:00 备份行
- [ ] DeepSeek 月费监控 · 看 `ai_usage_log` 表的累计 cost_cny
- [ ] 飞书 / TG 推送配置可发测试消息

---

## 备注

- 本文档不执行部署 · 等产品负责人提供阿里云账号 + 域名后,按章节顺序逐步操作
- 第一次部署预计 4-6 小时 · 主要时间花在 DNS 生效 + LE 证书申请 + 实际跑通
- 不要把生产 .env / backup.env 上传 GitHub(已在 .gitignore)
- 不要给 ossutil 用主账号 AccessKey · 必须 RAM 子账号 + 最小权限
