# 点金 Midas · 部署前置清单(给产品负责人)

部署执行手册 `docs/deployment-runbook.md` 开跑前,以下凭证 / 配置必须就绪。
按本清单一项项准备,准备齐了告诉 Claude 「凭证齐」,然后一起按 runbook 走。

---

## 0 · 部署模式(开 runbook 前先拍)

两种模式选一,影响 DNS 配法 + 是否要 Vercel 账号:

| 维度 | 模式 A · Vercel + VPS(推荐) | 模式 B · VPS 全栈 |
|---|---|---|
| 前端 CDN | ✅ Vercel 全球边缘 | ❌ 单点香港 |
| 自动构建 / PR preview | ✅ git push 即部署 | ❌ 手动 docker rebuild |
| VPS 资源 | ~5.5GB | ~6.3GB(留 1.7GB 余量) |
| 依赖外部 | Vercel(免费档) | 完全自主 |
| 国内访问体验 | 优 | 仍可接受(香港直连) |
| DNS 配法 | `api` → VPS · `@/www` → Vercel | `api / @ / www` 全 → VPS |

**默认推荐模式 A** · 部署时告诉 Claude 「模式 A」或「模式 B」 · runbook 会按你选的分叉走。
切换无锁:模式 A 出问题随时可切 B(`docker compose --profile self-hosted up` 即可),反之亦然。

---

## 1 · DNS 子域名方案

**域名:** `midastrade.asia` · 你已注册。

**3 条解析必配(按 § 0 模式选择分两种配法):**

### 模式 A · Vercel + VPS

| 类型 | 主机记录 | 指向 | 用途 |
|---|---|---|---|
| `A` | `api` | `8.210.156.91` | 后端 API · Caddy 反代到 VPS |
| `A` 或 `CNAME` | `@`(根域名)| Vercel 提供的值(通常 `76.76.21.21`) | 首页 / Web 端 · 走 Vercel |
| `CNAME` | `www` | `cname.vercel-dns.com.` | 兼容 `www.midastrade.asia` 也能访问 |

### 模式 B · VPS 全栈

| 类型 | 主机记录 | 指向 | 用途 |
|---|---|---|---|
| `A` | `api` | `8.210.156.91` | 后端 API · Caddy 反代到 VPS |
| `A` | `@`(根域名)| `8.210.156.91` | 首页 / Web 端 · 同一台 VPS 上 Next.js |
| `A` 或 `CNAME` | `www` | `8.210.156.91`(或 CNAME `midastrade.asia.`)| Caddy 301 重定向到主域 |

**操作步骤(在域名注册商后台):**

### 步骤 A · 后端 API(现在就能配)
```
类型: A
主机记录: api
记录值: 8.210.156.91
TTL: 600(便于排错 · 后期可改 3600)
```

配完在本机验证:
```bash
dig api.midastrade.asia +short
# 应该返回: 8.210.156.91
```

### 步骤 B · 前端域名(等 Vercel 创建项目后配)

Vercel 后台导入 GitHub repo 后,会在 `Project → Domains → Add Domain` 提示你加一条:

**根域名 `midastrade.asia`:** Vercel 通常给两种选项:
- 推荐 `A` 记录 → `76.76.21.21`(Vercel anycast IP)
- 或 `CNAME @ → cname.vercel-dns.com.`(部分注册商支持 CNAME flatten)

**`www.midastrade.asia`:**
```
类型: CNAME
主机记录: www
记录值: cname.vercel-dns.com.
TTL: 600
```

**验证(Vercel 后台会自动检测):** Domains 页面 status 变 ✅ Active。

---

## 2 · GitHub Repo 访问

服务器要 `git clone` 你的私有 repo。两种方式选一:

### 方式 1 · Personal Access Token(简单)
1. GitHub → Settings → Developer settings → Personal access tokens → Generate new token (classic)
2. 勾 `repo` scope
3. 复制 token(只显示一次)· 形如 `ghp_xxxx`
4. clone 命令:`git clone https://<token>@github.com/<user>/midas.git`

### 方式 2 · Deploy Key(更安全 · 推荐)
1. 在服务器跑 `ssh-keygen -t ed25519 -f /root/.ssh/midas_deploy -N ""`
2. `cat /root/.ssh/midas_deploy.pub` 复制公钥
3. GitHub → repo → Settings → Deploy keys → Add deploy key · 粘贴公钥(只勾「Read access」)
4. 服务器 `~/.ssh/config` 加:
   ```
   Host github.com
       IdentityFile /root/.ssh/midas_deploy
       User git
   ```
5. clone:`git clone git@github.com:<user>/midas.git`

---

## 3 · 阿里云 OSS(每日备份)

1. **创建 bucket:**
   - 阿里云控制台 → OSS → 创建 Bucket
   - 名称:`midas-backup-hk`(全局唯一 · 已被占用可换)
   - 地域:**香港**(跟 VPS 同 region · 内网流量免费)
   - 存储类型:标准
   - 读写权限:**私有**(不能 public!)
   - 服务端加密:推荐 KMS

2. **创建 RAM 子账号 + AccessKey:**
   - 控制台 → RAM 访问控制 → 用户 → 创建用户
   - 用户名:`midas-backup`
   - 访问方式:✅ 使用永久 AccessKey 访问 API
   - 复制 AccessKey ID + Secret(只显示一次)
   
3. **授权 RAM 子账号(最小权限):**
   - 创建自定义权限策略 · JSON 模式:
   ```json
   {
     "Version": "1",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "oss:PutObject",
           "oss:ListObjects",
           "oss:DeleteObject",
           "oss:GetObject"
         ],
         "Resource": [
           "acs:oss:*:*:midas-backup-hk",
           "acs:oss:*:*:midas-backup-hk/*"
         ]
       }
     ]
   }
   ```
   - 命名 `MidasBackupPolicy` · 关联到 `midas-backup` 子账号

4. **设 OSS 生命周期规则(自动清理 > 7 天)**:
   - Bucket 基础设置 → 生命周期 → 创建规则
   - 前缀:`postgres/`
   - 文件过期时间:7 天后自动删除
   - 这层兜底 · 备份脚本里的清理逻辑作为 fallback

**填入 `/etc/midas/backup.env`:**
```bash
OSS_ENDPOINT=oss-cn-hongkong-internal.aliyuncs.com
OSS_BUCKET=midas-backup-hk
OSS_ACCESS_KEY_ID=<AccessKey ID>
OSS_ACCESS_KEY_SECRET=<AccessKey Secret>
```

---

## 4 · Google OAuth 配置(M1 第三波)

**目标:** 让用户能用 Google 账号登录 · 邮箱密码登录方式并存。

### 步骤 A · Google Cloud Console 创建项目

1. 访问 https://console.cloud.google.com/
2. 创建新项目 · 名称 `midas-prod`(或任意)
3. 启用 API:Google → Library → 搜 `Google Identity` / `OAuth2` · 不需要额外启用(OAuth client 创建后默认可用)

### 步骤 B · OAuth Consent Screen

1. APIs & Services → OAuth consent screen
2. User Type:**External**(允许任何 Google 用户登录)
3. App information:
   - App name: `点金 Midas`
   - User support email: 你的邮箱
   - Developer contact: 你的邮箱
4. App domain:
   - Application home page: `https://midastrade.asia`
   - Application privacy policy: `https://midastrade.asia/#`(M2+ 填实际 /privacy)
   - Application terms of service: `https://midastrade.asia/#`
5. Authorized domains: `midastrade.asia`
6. Scopes:**默认 3 个**(`userinfo.email` · `userinfo.profile` · `openid`)· 不要加更多
7. Test users(只在 Publishing status = Testing 时需要):加你自己的 Google 邮箱
8. Save

**Publishing status:** 测试期保持 `Testing` · 上线给真实用户前点 `Publish App`(审核可能 2-3 天 · 普通应用基本秒过)。

### 步骤 C · 创建 OAuth 2.0 Client ID

1. APIs & Services → Credentials → Create credentials → OAuth client ID
2. Application type:**Web application**
3. Name:`midas-web`
4. **Authorized JavaScript origins:**
   ```
   https://midastrade.asia
   https://www.midastrade.asia
   ```
5. **Authorized redirect URIs:**
   ```
   https://midastrade.asia/api/auth/callback/google
   https://www.midastrade.asia/api/auth/callback/google
   ```
   (NextAuth v5 固定路径 · 不能改)
6. Create
7. 弹窗显示 **Client ID** + **Client secret** · 复制两个值

### 步骤 D · 填到 Vercel + 服务器 .env

**Vercel** (Settings → Environment Variables · Production 环境):
- `GOOGLE_CLIENT_ID` = `<Client ID>`
- `GOOGLE_CLIENT_SECRET` = `<Client secret>`

**服务器 `/opt/midas/.env`:**
- `GOOGLE_CLIENT_ID` = `<Client ID>`(后端验签 id_token 时用 · 必须跟 Vercel 端一致)
- `GOOGLE_CLIENT_SECRET` = `<Client secret>`(后端不实际用 · 写一份方便对照)

### 步骤 E · 本地 dev 期间(可选)

如果你想在 dev 环境也测 Google 登录:
- 复用同一个 OAuth client(简单)
- 或单独建一个 `midas-dev` client · Authorized redirect URI 加 `http://localhost:3000/api/auth/callback/google`

---

## 5 · Resend 邮箱

确认 dev 用的 `RESEND_API_KEY` 是否够生产量(免费档每天 100 封)· 如果不够,在 Resend 后台:
1. Domains → Add Domain → `midastrade.asia`
2. 按指引在域名注册商加 3 条 TXT 记录(SPF + DKIM)
3. 状态变 ✅ Verified 后 · `EMAIL_FROM` 可改成 `noreply@midastrade.asia`(否则邮件容易进垃圾箱)

---

## 6 · 服务器初始安全(可选 · 但推荐)

阿里云轻量默认 root 密码登录 · 上线前建议:
- 上传你的 SSH 公钥到 `/root/.ssh/authorized_keys`
- 关密码登录:`PasswordAuthentication no` 在 `/etc/ssh/sshd_config` 改 · `systemctl restart sshd`
- 改默认 root 密码 / 改 SSH 端口(可选)

---

## 7 · 上线前 .env 项检查表(凭证清单)

按这个表勾完 · 才能开 runbook STEP 8。

| 凭证项 | 哪里拿 | 备注 |
|---|---|---|
| `SECRET_KEY` | `openssl rand -hex 32` 服务器生成 | runbook STEP 8 |
| `POSTGRES_PASSWORD` | `openssl rand -hex 16` 服务器生成 | 跟 DATABASE_URL 必须一致 |
| `CLICKHOUSE_PASSWORD` | `openssl rand -hex 16` 服务器生成 | |
| `RESEND_API_KEY` | Resend 控制台 | dev 用的可复用 |
| `EMAIL_FROM` | `noreply@midastrade.asia` | 等 SPF/DKIM 验证后能用 |
| `DEEPSEEK_API_KEY` | 你 dev 用的那个 | 同一 key 可复用 · M2+ 可建生产专用 |
| `GOOGLE_CLIENT_ID` | § 4 步骤 C | Vercel + 服务器都要 |
| `GOOGLE_CLIENT_SECRET` | § 4 步骤 C | 同上 |
| `OSS_ACCESS_KEY_ID` | § 3 步骤 2 | 只在 `/etc/midas/backup.env` |
| `OSS_ACCESS_KEY_SECRET` | § 3 步骤 2 | 同上 |
| GitHub PAT 或 deploy key | § 2 | 服务器拉 repo 用 |

---

## 8 · M1-G 预登记(部署完成后立刻启动)

**2026-05-21 拍板:** 推送当前是「用户自带 bot」模式(每个用户自己去 @BotFather 建 bot · 自己填 token + chat_id)· 上线先用此模式 · 部署完立刻改造为标准 SaaS 「统一 bot + /start 绑定」模式。

**M1-G Checkpoint 范围:**

- ① 用 @BotFather 建 `@MidasTradeBot` (或类似名) · 拿全局 token
- ② `settings.TG_BOT_TOKEN` 改全局 env
- ③ alembic migration:`notification_config` 删 `tg_bot_token` 列 + 新增 `tg_binding_code`(临时绑定码)
- ④ `POST /api/v1/notifications/telegram/bind/start` · 生成 6 位 code 入 Redis(TTL 10min)+ 返 deep link `https://t.me/MidasTradeBot?start=<code>`
- ⑤ `POST /api/v1/notifications/telegram/webhook` · 接 TG `/start` command · 提取 `chat.id` · 用 binding_code 找到 user · 写 `tg_chat_id` · 回 「绑定成功 ✓」
- ⑥ Dispatcher 简化 · 用全局 token + 用户 chat_id
- ⑦ 前端 `/settings` Telegram section 重写 · 「绑定 Telegram」按钮 + 已绑定状态 + 解绑
- ⑧ 飞书清理:后端 client/dispatcher/templates 删 feishu 分支 · 前端删 feishu section · `feishu_webhook_url` 字段保留(下兼容)
- ⑨ ADR 0009 v2 追加 「2026-05-21 飞书移除 + 统一 bot 模式」 节
- ⑩ pytest + 真机绑定测试一次

**估时:** 7-8h · webhook 路线 · 依赖 HTTPS 已就绪(STEP 13 装完 Caddy 后即可 `setWebhook`)

**飞书结论:** 飞书自定义机器人只能推群 · 不能私聊 C 端用户 · 企业自建应用又强制组织内成员 · **不适合 C 端 SaaS 用户级推送** · M1-G 彻底移除。

**M1 上线只保留 Telegram 推送通道。**

---

## 9 · 启动信号

凭证齐了告诉 Claude 「**runbook 可以开跑**」· 我会:
1. 跟你过一遍 STEP 1 SSH
2. 一步一步给命令 · 你贴输出 · 我诊断
3. 遇到任何报错都贴给我 · 不要自己改命令

**预计总时长:** 1.5 - 3 小时(取决于 DNS 生效 + Resend 域名验证速度)。
