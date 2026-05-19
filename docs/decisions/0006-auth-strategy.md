## 0006 · 鉴权策略

### 状态
Approved (2026-05-19)

### 上下文
M0 验收第 2 步「陌生人能注册 → 邮箱验证 → 登录」必须打通。Task 3.5 (Checkpoint N) 落地。
04 文档原列了 NextAuth.js v5 但没给 provider / 邮件源 / 密码哈希 / session 策略的具体选择。

### 决策

#### 1. 邮件 provider
- **主用 Resend**(免费 100 封/天,API 干净 · 比 SMTP 配置少)
- 备用 Postmark(生产环境若需要更高送达率)
- 应急 SMTP(任何邮箱服务,适配 self-host)
- env:`RESEND_API_KEY` + `EMAIL_FROM`(显示发件人,如 `noreply@midas.example`)

#### 2. 密码哈希
- **argon2id**(passlib 已经在 apps/api/pyproject.toml,无新依赖)
- 优于 bcrypt:更新设计,memory-hard,默认参数已经够强
- 不强制特殊字符(用户体验优先);8+ 字符长度

#### 3. NextAuth Session 模型
- **Database session**(NextAuth v5 默认),不是 JWT-only
- 理由:可主动失效(攻击响应)、可查活跃会话、可审计
- Postgres 表:`user_session`(NextAuth schema 标准),由 NextAuth 直接写
- 滑动过期:7 天(每次访问刷新)

#### 4. 前后端 token 流
- NextAuth 给浏览器 cookie(httpOnly + secure + sameSite=lax)
- 浏览器→FastAPI:用 NextAuth 的 `session.token.accessToken`(短 JWT, 1h TTL)作为 Bearer
- FastAPI `python-jose` 用同 secret `SECRET_KEY` 验签,取 `sub=user_id`
- 不直接共享 Postgres 表(NextAuth 用其 ORM 写 session,FastAPI 不读 `user_session` 表)

#### 5. 邮箱验证策略
- **强制**:User 表 `email_verified_at` 字段,NULL = 未验证,**未验证不让登录**
- 注册立即发链接邮件 `https://midas.example/verify-email?token=<one-time>`
- token 24h 有效;过期或丢失可在 /login 重新发送
- 允许注册后 24h 内 retry 发送邮件(避免恶意刷邮件)

#### 6. 注册要求
- 邮箱(唯一)+ 密码(8+ 字符)
- **18+ 强制勾选**(合规要求,模拟交易也要)
- 不做 captcha(M0 不接收注册量,M2+ 引入 Turnstile)
- 不要手机号(M0 简化)

#### 7. 不做的事(M0 红线)
- Google / GitHub OAuth(M3+)
- 2FA / TOTP(M2+)
- 忘记密码自动重置(M0 用户找客服;M1+ 实装)
- 用户头像 / 个人资料页(M0 不需要)
- 注册赠送虚拟金弹窗(虚拟账户初始 100 万,Task 5 自动建)

#### 8. 路由保护策略
- 未登录访问 `/workbench` / `/dashboard` 等 → 重定向 `/login?next=...`
- 已登录访问 `/login` / `/register` → 重定向 `/workbench`
- 实现:Next.js middleware.ts 拦截

#### 9. 邮件模板视觉
- 沿用 Task 3 token 系统:中国红主色 + 帝王金签名 + 衬线大字标题
- 不要默认蓝色 / 不要 emoji 堆砌
- 体积 < 50KB(含内联 logo)

### 影响范围
- **Task 3.5 N · 鉴权地基实装**(全部上面 9 点)
- **Task 4 自选股** · 依赖 `user_id`(`watchlist_group.user_id FK`)
- **Task 5 虚拟交易** · 依赖 `user_id`(`virtual_account.user_id` 唯一)
- **Task 6 推送** · 用户配置飞书/TG 跟 user 绑定

### 撤销路径
1. **换邮件 provider:** 改 Resend SDK 调用 → Postmark/SMTP,env 改对应 key
2. **换密码哈希:** passlib `argon2id` → `bcrypt`,登录时旧 hash 自动 rehash 升级
3. **切 JWT-only session:** NextAuth 配置 `session: { strategy: 'jwt' }`,删 `user_session` 表
4. **取消邮箱验证强制:** `email_verified_at` 字段允许 NULL,登录跳过检查
5. **加 OAuth(未来):** NextAuth providers 加 GoogleProvider / GitHubProvider,无需破坏既有邮箱密码路径
