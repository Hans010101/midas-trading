# 点金 Midas · 部署执行手册(Runbook)

**目标:** 把 `midastrade.asia` 域名指向真实服务,前端 Vercel + 后端阿里云香港 VPS,从零部署到验收通过。

**协作模式:** Claude Code 不直接 SSH。每一步,Claude 给出命令,你在服务器粘贴执行,把输出贴回。任何报错由 Claude 诊断。

**服务器规格:** 阿里云轻量 香港 · 4 vCPU · 8GB RAM · 70GB SSD · Ubuntu 24.04 · IP `8.210.156.91`

---

## ⭐ STEP 0 · 部署模式选择(开 runbook 前先拍)

两种模式 · 后续步骤会按你选的分叉:

### 模式 A · Vercel + VPS(推荐)

```
浏览器 ──HTTPS──> Vercel(midastrade.asia / www.)        ← 前端 · 走 Vercel CDN
                   │
                   └── 同源 API 调用 ──HTTPS──> Caddy(api.midastrade.asia)  ← VPS
                                                  │
                                                  └── 反代 127.0.0.1:8000(midas-api)
                                                                          │
                                                                          ├── midas-postgres
                                                                          ├── midas-clickhouse
                                                                          ├── midas-redis
                                                                          └── midas-worker
```

### 模式 B · VPS 自托管全栈

```
浏览器 ──HTTPS──> Caddy(midastrade.asia / www.) ──> 127.0.0.1:3000(midas-web)    ← VPS · 前端
              ──> Caddy(api.midastrade.asia)    ──> 127.0.0.1:8000(midas-api)    ← VPS · 后端
                                                       │
                                                       ├── midas-postgres
                                                       ├── midas-clickhouse
                                                       ├── midas-redis
                                                       └── midas-worker
```

### 选型对比

| 维度 | 模式 A · Vercel + VPS | 模式 B · VPS 全栈 |
|---|---|---|
| **前端 CDN** | ✅ Vercel 全球边缘 · 国内访问由 Vercel 路由 | ❌ 单点香港 · 国内 ~80-150ms |
| **自动构建 / 预览** | ✅ git push 自动 build · PR preview | ❌ 手动 `docker compose up --build` |
| **资源占用(VPS)** | ~5.5GB(5 服务) | ~6.3GB(6 服务 · web 占 ~768MB)|
| **运维复杂度** | 低 · 前端零运维 | 中 · 一台机管所有 |
| **依赖外部服务** | 依赖 Vercel(免费档够用) | 完全自主 · 仅依赖 OSS 备份 |
| **DNS 记录** | `api` 指 VPS · `@/www` 指 Vercel | `api` / `@` / `www` 全指 VPS |
| **首屏延迟** | Vercel edge 优 | 直连香港 · 仍可接受 |
| **成本** | $0(Vercel Hobby)+ VPS | 仅 VPS |
| **何时选 B** | Vercel 在国内被墙 / 想保留所有数据自主 / 上线后 Vercel 限流 | |

**默认推荐 A** · 资源富余 + 国内访问体验更好 + Vercel 在国内目前可用。**M1 上线选 A** · 后续 Vercel 出问题可无缝切 B(代码里 `web` service 已经准备好)。

### 拍板信号

告诉 Claude 「**模式 A**」或「**模式 B**」 · runbook 后续每个步骤会按这个分叉。

---

---

## ⚠ 前置条件 · 开始前必须就绪

| 项 | 状态 | 说明 |
|---|---|---|
| DNS A 记录 `api.midastrade.asia` → `8.210.156.91` | 你去注册商配 | TTL 设 600s 便于排错 · 两种模式都要 |
| DNS `midastrade.asia` + `www` → Vercel(模式 A)或 → `8.210.156.91`(模式 B) | 你去注册商配 | 按 STEP 0 选的模式配 |
| 阿里云 OSS 香港 region bucket `midas-backup-hk` | 你创建 | 用于 pg_dump 每日备份 |
| 阿里云 RAM 子账号 + AccessKey(权限:OSS PutObject/ListObjects/DeleteObject)| 你创建 | 不能用主账号 key |
| GitHub repo 私有 / 可访问 | 你确认 | runbook 会用 git clone |
| GitHub deploy key 或 PAT | 你创建 | 服务器拉私有 repo 用 |
| Google Cloud Console OAuth 2.0 client | 你配 · 详见 § Google OAuth 配置 | M1 第三波 |
| Resend API Key | 你确认 dev 用的 key 是否够 prod 量 | 邮箱验证用 |

---

## STEP 1 · SSH 登录服务器

**目的:** 进入服务器 · 后续所有命令都在 SSH 会话里跑。

**你跑(本机)**:
```bash
ssh root@8.210.156.91
```

阿里云轻量默认 root 登录(或你给定的用户名)· 接受 ECDSA fingerprint(`yes`)。

**期望输出:**
```
Welcome to Ubuntu 24.04 LTS
Last login: ...
root@iZxxxxxZ:~#
```

**❌ 如果失败:**
- `Connection refused` → 阿里云控制台检查 22 端口是否在防火墙开放
- `Permission denied (publickey)` → 没有上传 SSH 公钥;阿里云控制台用 VNC 临时登录 + `~/.ssh/authorized_keys` 加你的公钥

---

## STEP 2 · 系统更新 + 基础工具

**你跑:**
```bash
apt update && apt upgrade -y
apt install -y curl wget git vim ca-certificates gnupg lsb-release
```

**期望:** 几分钟跑完 · 末尾不见 ERR / fatal · 看到 `Reading package lists... Done` 类似输出。

---

## STEP 3 · 安装 Docker + Compose plugin

**你跑(官方 convenience script · Ubuntu 24.04 兼容):**
```bash
curl -fsSL https://get.docker.com | sh
docker --version
docker compose version
systemctl enable --now docker
```

**期望:**
```
Docker version 27.x.x, build ...
Docker Compose version v2.x.x
```

**❌ 如果失败:**
- `Cannot connect to the Docker daemon` → `systemctl status docker` 看日志
- 阿里云镜像源慢 → 用 `curl -fsSL https://get.docker.com -o get-docker.sh && DOWNLOAD_URL=https://mirrors.aliyun.com/docker-ce sh get-docker.sh`

---

## STEP 4 · 安装 Caddy(HTTPS 自动证书)

**你跑:**
```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install -y caddy
caddy version
systemctl status caddy --no-pager | head -5
```

**期望:**
```
v2.x.x ...
● caddy.service - Caddy
   Loaded: loaded ...
   Active: active (running) ...
```

---

## STEP 5 · 安装 ossutil(阿里云 OSS CLI · 备份用)

**你跑:**
```bash
wget -O /tmp/ossutil https://gosspublic.alicdn.com/ossutil/1.7.18/ossutil64
install -m 0755 /tmp/ossutil /usr/local/bin/ossutil
ossutil --version
```

**期望:** `ossutil version: 1.7.x`

---

## STEP 6 · 防火墙规则(阿里云轻量安全组)

⚠ **不在 SSH 里改 ufw**(可能锁自己出来) · 走阿里云控制台:

**你做:**
- 阿里云控制台 → 服务器 → 防火墙 → 规则
- 入站只放行:`22/tcp`(SSH)· `80/tcp`(HTTP→HTTPS redirect)· `443/tcp`(HTTPS)
- 其余端口(5432 / 6379 / 8123 / 8000)**全部不对外**

**贴回:** 截图安全组规则给我看 · 我帮你确认。

---

## STEP 7 · 拉代码到服务器

**你跑(替换 GitHub URL · 用 deploy key 或 PAT):**
```bash
mkdir -p /opt && cd /opt
git clone https://github.com/<你的账号>/midas.git
# 或私有 + PAT:
# git clone https://<PAT>@github.com/<你的账号>/midas.git
cd /opt/midas
git log --oneline -5
```

**期望:** 看到最近 5 个 commit · 末尾包含 `M1-E v4` 等字样。

**❌ 如果失败:**
- `repository not found` → repo 路径错;或权限不够(PAT 没勾 repo 权限)
- 网速慢 → 国内 GitHub 慢是常态 · 可换 SSH:`git clone git@github.com:...`(需服务器有 deploy key)

---

## STEP 8 · 准备生产 .env(本步骤最关键 · 慢慢做)

**你跑:**
```bash
cd /opt/midas
cp .env.example .env
openssl rand -hex 32   # 生成 SECRET_KEY · 复制这个值
```

**贴回:** 把 `openssl rand -hex 32` 的输出给我(无害可贴,只是随机字符串)· 我会告诉你怎么填到 .env。

**你跑(编辑 .env):**
```bash
vim /opt/midas/.env
```

**.env 必须设的项**(下面给完整模板,把占位符替换成真值):

```bash
# === 应用 ===
DEBUG=false

# === Postgres(docker 内部 DNS · 不暴露)===
POSTGRES_DB=midas
POSTGRES_USER=midas
POSTGRES_PASSWORD=<openssl rand -hex 16 生成一个>
DATABASE_URL=postgresql+asyncpg://midas:<上面同一个密码>@postgres:5432/midas

# === ClickHouse ===
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=default
CLICKHOUSE_USER=midas
CLICKHOUSE_PASSWORD=<openssl rand -hex 16 生成一个>

# === Redis / Celery ===
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# === JWT / Session 密钥 ===
SECRET_KEY=<STEP 8 的 openssl 输出 · 64 字符 hex>
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# === CORS · 严格匹配前端域名(两种模式相同)===
CORS_ORIGINS=["https://midastrade.asia","https://www.midastrade.asia"]

# === 公开 URL(给前端 SSR + 邮件链接)===
PUBLIC_WEB_URL=https://midastrade.asia
NEXT_PUBLIC_API_URL=https://api.midastrade.asia
# 模式 B 额外:web 容器 SSR 内部调 API 用 docker 内部 DNS
# API_INTERNAL_URL=http://api:8000   ← 模式 B 才需要 · 模式 A 不要这行

# === Resend 邮件验证 ===
RESEND_API_KEY=<你的 Resend key>
EMAIL_FROM=noreply@midastrade.asia

# === AI 决策卡(DeepSeek)===
DEEPSEEK_API_KEY=<你的 DeepSeek key>
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek/deepseek-chat
LLM_MAX_TOKENS=1024
LLM_TIMEOUT_SECONDS=30
LLM_MONTHLY_BUDGET_CNY=200
LLM_MOCK_MODE=false

# === Google OAuth(M1 第三波 · 详见 § Google OAuth 配置)===
GOOGLE_CLIENT_ID=<Google Console 拿到>
GOOGLE_CLIENT_SECRET=<Google Console 拿到>
```

**你做:** 保存退出(`:wq`) · 然后:
```bash
cat /opt/midas/.env | grep -E '^(SECRET_KEY|POSTGRES_PASSWORD|CLICKHOUSE_PASSWORD|DEEPSEEK|GOOGLE_CLIENT_ID|EMAIL_FROM)='
```

**贴回:** 输出(SECRET_KEY 等的实际值可以打码 / 只显示前 8 字符 + 长度) · 我确认结构对。

---

## STEP 9 · 准备 OSS 备份凭证

**你跑:**
```bash
mkdir -p /etc/midas
vim /etc/midas/backup.env
```

**填入(替换真值):**
```bash
OSS_ENDPOINT=oss-cn-hongkong-internal.aliyuncs.com
OSS_BUCKET=midas-backup-hk
OSS_ACCESS_KEY_ID=<RAM 子账号 AccessKeyId>
OSS_ACCESS_KEY_SECRET=<RAM 子账号 AccessKeySecret>
```

**你跑:**
```bash
chmod 600 /etc/midas/backup.env
chown root:root /etc/midas/backup.env
ls -la /etc/midas/backup.env
```

**期望:** `-rw------- 1 root root ...`

---

## STEP 10 · 启动 docker compose(生产 overlay)

**你跑:**
```bash
cd /opt/midas
docker compose \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.prod.yaml \
  pull
```

**期望:** Postgres / ClickHouse / Redis 镜像拉完(自有 build 的 api/worker 此步跳过)。

### [模式 A] build + up · 5 服务

```bash
docker compose \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.prod.yaml \
  up -d --build
```

**预计耗时:** 4-8 分钟。**期望:** 5 服务 `healthy`(postgres / clickhouse / redis / api / worker)。

### [模式 B] build + up · 6 服务(含 web)

```bash
docker compose \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.prod.yaml \
  --profile self-hosted \
  up -d --build
```

**预计耗时:** 10-18 分钟(web 多了 pnpm install + Next build · Next 镜像层第一次构建较慢)。**期望:** 6 服务 `healthy`(postgres / clickhouse / redis / api / worker / web)。

### 验证(两模式相同)

```bash
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml ps
```

**❌ 如果 ClickHouse 起不来 / OOM:**
```bash
docker logs midas-clickhouse 2>&1 | tail -50
```
- 看 `Memory limit exceeded` → 已经在 prod.yaml 限了 2G · 不应该再 OOM
- 看 `Cannot bind` → 端口冲突 · 但 prod 不暴露端口 · 不应该
- 贴日志给我

---

## STEP 11 · Alembic 数据库迁移

**你跑:**
```bash
docker exec midas-api alembic upgrade head
```

**期望:**
```
INFO  [alembic.runtime.migration] ...
INFO  [alembic.runtime.migration] Running upgrade ... -> d8e2f4a5c7b9, user google oauth ...
```

末尾 head 应该是 `d8e2f4a5c7b9_user_google_oauth.py`(M1 第三波最新 migration)。

**❌ 如果失败:**
- `relation "alembic_version" does not exist` → 数据库连接没问题但表没建 · alembic upgrade head 会自动建 · 重试一次
- `password authentication failed` → POSTGRES_PASSWORD 跟 DATABASE_URL 不一致 · 检查 .env

---

## STEP 12 · 预热三市场 K 线数据

**你跑:**
```bash
docker exec midas-worker celery -A celery_app call tasks.market.backfill_demo_klines
```

**或手动跑回填脚本:**
```bash
docker exec midas-api python -m scripts.backfill_demo 2>&1 | tail -20
```

**(实际命令名取决于你 repo 里 scripts 目录的 backfill 入口 · 不确定就先跳过 · 用户访问时第一次会自动拉)**

**验证:**
```bash
curl -s "http://localhost:8000/api/v1/market/kline?symbol=NVDA&market=us&period=1d&limit=10" | python3 -m json.tool | head -30
```

**期望:** 返回 K 线 JSON · 至少有 5 根。

---

## STEP 13 · 配置 Caddy 反向代理(HTTPS 自动证书)

⚠ **前置:**
- 两种模式都要:`dig api.midastrade.asia +short` 返回 `8.210.156.91`
- 模式 B 额外:`dig midastrade.asia +short` + `dig www.midastrade.asia +short` 都返回 `8.210.156.91`

**你跑:**
```bash
vim /etc/caddy/Caddyfile
```

### [模式 A] 只代理 API 子域

```caddyfile
api.midastrade.asia {
    reverse_proxy 127.0.0.1:8000
    encode gzip

    # 给后端的真实 client IP
    header_up X-Real-IP {remote_host}

    # 安全 header(M2+ 可加 CSP 等)
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
    }

    handle_errors {
        respond "Upstream error: {http.error.status_code}" {http.error.status_code}
    }
}
```

### [模式 B] 代理 API 子域 + 主站 + www

```caddyfile
# API 后端
api.midastrade.asia {
    reverse_proxy 127.0.0.1:8000
    encode gzip
    header_up X-Real-IP {remote_host}
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
    }
    handle_errors {
        respond "Upstream error: {http.error.status_code}" {http.error.status_code}
    }
}

# 主站 · Next.js web 容器
midastrade.asia {
    reverse_proxy 127.0.0.1:3000
    encode gzip
    header_up X-Real-IP {remote_host}
    header_up X-Forwarded-Proto https
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
    }
}

# www 重定向到主站(SEO 一致性)
www.midastrade.asia {
    redir https://midastrade.asia{uri} permanent
}
```

**你跑:**
```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
journalctl -u caddy --no-pager | tail -20
```

**期望日志包含:**
```
... certificate obtained successfully ...
... served key authentication ...
```

**❌ 如果证书申请失败:**
- DNS 还没生效:`dig api.midastrade.asia +short` 必须返回 `8.210.156.91`
- 80 端口被占:`ss -tlnp | grep :80`(应该是 caddy)
- 阿里云防火墙没开 80/443:回 STEP 6

**验证(本机命令)**:
```bash
# 两种模式都要
curl -i https://api.midastrade.asia/health

# 模式 B 额外
curl -I https://midastrade.asia/
curl -I https://www.midastrade.asia/   # 应见 301 → midastrade.asia
```

**期望:** `api.midastrade.asia/health` 返 `HTTP/2 200` + `{"status":"ok","service":"midas-api"}` · 模式 B 主站返 200 + Next.js HTML。

---

## STEP 14 · 配 cron 每日备份

**你跑:**
```bash
crontab -e
```

**追加:**
```
0 3 * * *  cd /opt/midas && /opt/midas/scripts/backup_postgres.sh >> /var/log/midas-backup.log 2>&1
```

**手动跑一次验证:**
```bash
/opt/midas/scripts/backup_postgres.sh 2>&1 | tail -20
```

**期望:**
```
[backup] start
[backup] dump OK · X.XM
[backup] uploaded → oss://midas-backup-hk/postgres/midas-pg-...sql.gz
[backup] local cleanup
[backup] done
```

**❌ 如果失败:**
- `ossutil command not found` → STEP 5 没装好
- `OSS 403` → AccessKey 错或者没授权 bucket
- `Container midas-postgres not found` → STEP 10 没起来

---

## STEP 15 · 前端部署

### [模式 A] Vercel

**你做(在 Vercel 后台):**
1. New Project → Import Git Repository
2. 选 `midas` repo
3. **Root Directory:** `apps/web`
4. **Framework Preset:** Next.js(自动)
5. **Build Command:** `cd ../.. && pnpm install --frozen-lockfile && pnpm --filter @midas/web build`
6. **Install Command:** `pnpm install`

**Vercel 环境变量(`Settings → Environment Variables`):**
| Key | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.midastrade.asia` |
| `API_INTERNAL_URL` | `https://api.midastrade.asia` |
| `AUTH_SECRET` | 跟服务器 .env 的 `SECRET_KEY` 同一个值 |
| `AUTH_TRUST_HOST` | `true` |
| `GOOGLE_CLIENT_ID` | Google Console 拿到 |
| `GOOGLE_CLIENT_SECRET` | Google Console 拿到 |

**自定义域名:**
- Vercel → Domains → Add `midastrade.asia` + `www.midastrade.asia`
- 按 Vercel 指引去 DNS 配 CNAME / A 记录

**点 Deploy · 等 build 完成。**

### [模式 B] VPS web 容器(STEP 10 已起 · STEP 13 Caddy 已代理)

模式 B 跳过 Vercel · STEP 10 的 `--profile self-hosted` 已经把 web 容器跑起来 · STEP 13 的 Caddy 已经把 `midastrade.asia` 反代到 `127.0.0.1:3000`。

**验证 web 容器在跑:**
```bash
docker logs midas-web 2>&1 | tail -20
docker exec midas-web wget -qO- http://localhost:3000/ | head -20
```

**期望:** Next.js 启动日志 `▲ Next.js 15.x.x ready in Xms` + 首页 HTML(`<!DOCTYPE html>` 开头)。

**❌ 如果 web 容器没起:**
- STEP 10 命令漏了 `--profile self-hosted` → 重跑 STEP 10 模式 B 命令
- Next build 失败 OOM(8G 可能不够双构建):`docker logs midas-web 2>&1 | grep -i heap` · 临时把 prod.yaml 里 web 内存限制提到 1.5G 再 build,build 完降回 768M

**模式 B 不需要 Vercel · 也不需要在 Vercel 配 env vars(env 全在服务器 .env 里 · `docker-compose.prod.yaml` 把 .env 注入 web 容器)。**

---

## STEP 16 · 端到端验收

**你做(浏览器):**
- [ ] `https://midastrade.asia/` → 首页加载 · 水墨 + 印章 + 三市通览 · TLS 锁正常
- [ ] `https://midastrade.asia/workbench` → 匿名可看 K 线 + 缠论 + AI 决策卡
- [ ] 切换 A 股 / 美股 / 加密 · 三市场 K 线都能加载
- [ ] 顶部 AI 信号条 + 右栏 AI 决策卡 · `llm_mode='real'`(无 mock 徽章)
- [ ] 点「买入」→ 未登录提示 + 跳 /login
- [ ] /register → 真实邮箱注册 → 收 Resend 验证邮件 → 点链接 → 跳 /login → 用密码登录
- [ ] /login 用 Google 登录 → Google 同意页 → 回跳 → 已登录态进 /workbench
- [ ] 登录后 /account → 设虚拟资金 → /workbench 下单 → 200 OK
- [ ] 服务器:`docker exec midas-postgres psql -U midas -d midas -c "SELECT email, google_sub IS NOT NULL AS via_google FROM \"user\";"` → 看到刚才的注册账号

---

## STEP 17 · 上线后监控基线

**你做:**
```bash
# 资源占用
docker stats --no-stream
# 模式 A 期望: clickhouse < 2G, postgres < 800M, redis < 300M, api < 1G, 总和 < 5.5G
# 模式 B 期望: 上述 + web < 800M, 总和 < 6.3G

# 日志检查
docker logs midas-api 2>&1 | tail -20
docker logs midas-worker 2>&1 | tail -20

# 备份验证(明早 03:30 之后跑)
tail -50 /var/log/midas-backup.log
ossutil ls oss://midas-backup-hk/postgres/ -s
```

---

## 故障排查附录

| 现象 | 第一步排查 |
|---|---|
| `502 Bad Gateway` from Caddy | `docker ps` 看 midas-api 是否 healthy · 没就 `docker logs midas-api` |
| `503 LLM unavailable` | 看 `/etc/midas/backup.env` 不,看 `.env` 里 `DEEPSEEK_API_KEY` 是不是空 |
| 用户注册 verification 邮件没收到 | Resend 控制台看 delivery logs · 99% 是 DNS SPF/DKIM 没配好 |
| Google OAuth 回调 redirect_uri_mismatch | Google Console 的 Authorized redirect URI 是否包含 `https://midastrade.asia/api/auth/callback/google` |
| ClickHouse OOM kill | `docker logs midas-clickhouse \| grep -i memory` · 调小 `CLICKHOUSE_MAX_SERVER_MEMORY_USAGE` |
| Postgres 连接打满 | `docker exec midas-postgres psql -U midas -c "SELECT count(*) FROM pg_stat_activity;"` · 看到 > 70 就要调 prod.yaml max_connections |

---

## 完成标志

- [x] 浏览器访问 `https://midastrade.asia` 出现首页
- [x] 浏览器访问 `https://midastrade.asia/workbench` 看到 K 线 + AI 决策卡
- [x] `https://api.midastrade.asia/health` 返回 `{"status":"ok"}`
- [x] 邮箱密码注册 + 验证邮件 + 登录走通
- [x] Google OAuth 登录走通
- [x] 第一份 OSS 备份明早 03:00 之后能在 oss 看到
