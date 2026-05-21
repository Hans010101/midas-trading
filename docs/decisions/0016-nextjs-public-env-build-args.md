# 0016 · Next.js NEXT_PUBLIC_* 必须走 Docker build ARG(2026-05-21 验收翻车)

## 状态
Recorded (2026-05-21)

## 事故

STEP 15 端到端验收 · 用户在 https://midastrade.asia/register 填邮箱/密码/
勾 18 岁/点「注册并发送验证邮件」 · 点击后**整个表单无任何反应**:
- 没有 success 提示
- 没有 error 提示
- 按钮 busy 短暂转一下回弹

后台 api 容器日志 0 调用 · Resend 没发邮件。

## 根因 · 两个 bug 叠加

### Bug 1 · NEXT_PUBLIC_API_URL 没作为 Docker build ARG 传

Next.js 的 `NEXT_PUBLIC_*` env 变量是**编译时 inline**到 client JS bundle,
不是 runtime 读 env。这是 Next.js 的设计约定:

- `process.env.API_INTERNAL_URL` → SSR / server-side · runtime env_file 生效
- `process.env.NEXT_PUBLIC_API_URL` → 编译时 inline 到 client bundle · **build 时必须有值**

我们的 `apps/web/Dockerfile` 漏写了 `ARG NEXT_PUBLIC_API_URL` · `pnpm build`
跑时 env 里没有这个值 · register 页面里的 `const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'` 编译后 bundle 里**写死了** `http://localhost:8000`。

浏览器跑 bundle · fetch 到 `http://localhost:8000/api/v1/auth/register` ·
浏览器的 localhost 是**用户自己电脑** · 不通(对方没起服务)· 浏览器立即
报 network error。

### Bug 2 · register 页 fetch() 没 try/catch

`apps/web/app/register/page.tsx:34-48` 原代码:
```typescript
try {
  const r = await fetch(...)
  if (!r.ok) { setError(body.detail); return }
  setSuccess('注册成功...')
} finally {
  setBusy(false)
}
```

只有 `try/finally` · 没 `catch`。fetch network error 直接 throw ·
传播为 unhandled promise rejection · setBusy(false) 跑 · 但 setError 没跑 ·
**UI 静默** · 用户以为按钮坏了。

两个 bug 叠加 = 「localhost 路径错」+「静默吞错误」 = 表单无响应。

## 修复

### 1. Dockerfile 加 ARG · build 时注入正确值

`apps/web/Dockerfile`:
```dockerfile
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
...
RUN echo "[build] NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL"
RUN cd apps/web && pnpm build
```

build 前 echo 一行 · 排错时能立即看到 build args 有没有传到。

### 2. docker-compose.yaml 通过 build.args 传

```yaml
web:
  build:
    context: ..
    dockerfile: apps/web/Dockerfile
    args:
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
```

注意:不是 `environment:` 块 · `environment:` 是 runtime · 对 NEXT_PUBLIC_* 已经晚了。

### 3. register page 加 catch · 让 fetch 异常被显式提示

```typescript
} catch (err) {
  const msg = err instanceof Error ? err.message : String(err)
  setError(`网络异常 · 请重试或联系管理员(${msg})`)
  console.error('[register] fetch failed:', err, 'API_BASE=', API_BASE)
} finally {
  setBusy(false)
}
```

后续任何 try 块都必须配 catch · 不能让 network/CORS/cert 错静默。

### 4. AUTH_URL 显式锁定(顺手修问题 1 OAuth redirect_uri_mismatch)

```yaml
web:
  environment:
    AUTH_URL: ${PUBLIC_WEB_URL:-https://midastrade.asia}
```

NextAuth v5 默认靠 Host 头反推 base URL · `AUTH_TRUST_HOST=true` 时
信任 X-Forwarded-Host/Proto · 但仍依赖 Caddy 透传正确。生产环境
**显式 AUTH_URL** 是最稳的 · 任何 header 透传变化都不影响。

## 教训

1. **Next.js NEXT_PUBLIC_* 是编译时 inline · 必须 build ARG · 不是 runtime env**
   这是 Next.js 跟 Docker 之间最经典的接缝坑 · 跟 0014(Compose .env 插值)
   同属「不同机制的 env 加载路径不一致」类。
2. **前端 try 必须配 catch · 不能只有 finally** · 静默吞错误比报错更糟糕 ·
   用户连「重试」的判断依据都没有。
3. **生产链路加显式锁定 · 不靠自动推断** · AUTH_URL / database URL / CORS
   origins 等都该写死真值 · 不靠 fallback。
4. **Dockerfile 里加 build-time echo** · 排错时一眼看到 ARG 有没有传到 ·
   `RUN echo "[build] NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL"` 这种调试痕迹
   保留下来,运维感激。

## 跟 0013/0014/0015 的关系

0013 · ports MERGE 没用 !override → 端口冲突
0014 · YAML 插值找不到 .env → 数据库密码 midas_dev
0015 · worker memory limit × concurrency 错配 → OOM
0016 · NEXT_PUBLIC_* 漏 build ARG → 前端 fetch 走 localhost

四个都属于「dev 默认值 vs prod 真值」错配 · dev 时不显眼 · prod 一上线
全暴露。教训:**写 prod overlay 时必须把 dev 时所有依赖默认值的地方
逐个审一遍**。

## 防御性补丁(M2 可加)

- `docker compose build` 阶段加 assert:build 完检查 web 镜像里 JS
  bundle 不含 `localhost:8000` 字样(grep -r "localhost:8000" dist/)
- update.sh 加 `--no-cache` 选项给运维(强制干净 rebuild)
- CI 跑 `next build` 时也加 `NEXT_PUBLIC_API_URL` env 检查 · 漏配立即 fail
