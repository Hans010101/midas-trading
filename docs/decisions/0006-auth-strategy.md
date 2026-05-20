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

## 偏离与回归路径

### 偏离 1 · M0 实际用 JWT session,不是 database session(2026-05-19)

**偏离原因:**
本 ADR 第 3 节决议「database session」,但 N Checkpoint 实装时改成了 NextAuth 默认的 **JWT session strategy**。理由:
- NextAuth v5 默认即 JWT,跨 ORM 写 NextAuth 的 `account/session/verification_token` 表会跟我们的 SQLAlchemy `users` 表打架
- database session 需要 Drizzle/Prisma 适配器,引入第二个 ORM 跟 FastAPI SQLAlchemy 并存,M0 阶段不值得
- M0 是「端到端走通」阶段,JWT 已足够支撑完整链路

**M0 接受的取舍:**
- 不能主动失效会话(被泄露的 JWT 在 TTL 内仍有效;7d TTL 限制最大暴露窗口)
- 不能查询活跃会话列表(产品功能,M0 不需要)
- 不能审计单次登录(JWT 无服务端记录)

**触发回归 DB session 的条件(任一即可):**
- 用户量 > 100 真实用户(单次 leak 影响面增大)
- 安全审计明确要求服务端会话管控
- 产品需要「管理员强制踢人」/「显示已登录设备」功能
- 出现 token 被泄露事件

**回归路径(预估 1.5 天):**
1. `pnpm add @auth/drizzle-adapter drizzle-orm` + `pnpm add -D drizzle-kit`
2. 写 NextAuth schema 的 Drizzle 定义(account/session/verification_token 4 张表)
3. `drizzle-kit push` 落到 Postgres(跟 SQLAlchemy 共存,不冲突)
4. NextAuth 配置 `adapter: DrizzleAdapter(db)` + `session: { strategy: 'database' }`
5. 兼容性:已有 JWT cookie 在切换后失效,所有用户需重新登录(一次性退出公告)
6. 后端 `get_current_user` 改为查 Drizzle 的 `session` 表(而非验 JWT),需要写新的 `verify_session_id` 路径

**保留 JWT 路径:**
即便切到 DB session,前端调 FastAPI 时仍用短期 JWT(NextAuth `getToken` 派发),后端验签不变。DB session 只管 NextAuth 自己的 cookie。

## OAuth 计划

### Task 7.1 引入 Google OAuth(M0 不做,留档)

**M0 不做的理由:**
- M0 阶段邮箱密码已能完整跑通验收链路(注册 → 邮箱验证 → 登录 → /workbench)
- OAuth 引入 3 个新问题,都在 M0 是低 ROI:
  - **`redirect_uri` 配置摩擦**:Google Console 注册的 redirect_uri 是固定的,本地 dev(localhost) + Vercel preview + 生产域名各要一组,M0 还没有稳定生产域名
  - **OAuth 用户的 `email_verified` 分支**:Google 已验邮箱,我们的 `email_verified_at` 字段要直接填,不走 verification_token 路径,代码多一个分支
  - **跨开发/生产域名同步**:Vercel 部署后 redirect_uri 又要改,流程上需要额外的 release checklist

**Task 7.1 引入的实施方案:**
- **复用 CryptoSharp 现有 Google client_id**(产品负责人决策,可省一次 Google Console 注册申请)
- redirect_uri 统一在生产域名(`midas.so` 或最终域名)注册,一次性配好 dev/preview/prod 三组
- OAuth 用户跳过邮箱验证(`email_verified_at = func.now()` 注册时直接填)
- **邮箱密码登录保留**(给不想用 Google 的用户 / 国内用户访问 Google 不畅的场景)
- 实装在 NextAuth v5 配置的 `providers` 数组里加 `GoogleProvider`:

  ```ts
  // apps/web/auth.ts
  import GoogleProvider from "next-auth/providers/google"

  providers: [
    CredentialsProvider({ /* 已存在 */ }),
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      // OAuth 用户自动 email_verified
    }),
  ]
  ```

- 后端 `/api/v1/auth/oauth-sync` 新增端点:NextAuth 拿到 Google profile 后调一次,后端 upsert `users` 表 + 标记 email_verified_at + 派发 JWT

**时机选择:**
Task 7.1 是「视觉营销 + 上线准备」阶段,届时:
- 生产域名已敲定
- Google Console redirect_uri 一次性配齐
- 上线公告里宣传「也支持 Google 一键登录」是个不错的 marketing 卖点
