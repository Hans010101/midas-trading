# syntax=docker/dockerfile:1.7
# ↑ BuildKit 语法 · 使能 RUN --mount=type=cache(ADR 0031 DP3 / 对齐 api/worker)
# 点金 Midas · web 多阶段构建
# 构建上下文:仓库根目录(..)
# 构建命令:docker build -f apps/web/Dockerfile -t midas-web ..

# === Stage 1: builder ===
FROM node:20-alpine AS builder
WORKDIR /repo

# Next.js NEXT_PUBLIC_* 是 build-time inline · 必须在 build 前注入到 env ·
# runtime env_file 没用(Next 已经把值编译进 JS bundle)· 0016 ADR
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN corepack enable && corepack prepare pnpm@10.32.1 --activate

# 先拷 manifest 利用 Docker 层缓存
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json turbo.json ./
COPY apps/web/package.json ./apps/web/
COPY packages/shared/package.json ./packages/shared/

# ── ADR 0031 DP3 · pnpm store BuildKit cache mount ──
# Docker root user 下 pnpm v10 默认 store 在 /root/.local/share/pnpm/store
# sharing=locked 跟 api/worker 已实证模式一致 · tarball 复用 · 不写入镜像层
# 预期:rebuild 时 pnpm install 30-60s → 5-10s(只 link node_modules · tarball 全 cache 命中)
RUN --mount=type=cache,target=/root/.local/share/pnpm/store,sharing=locked \
    pnpm install --frozen-lockfile

# 拷 web + 共享包源码
COPY apps/web ./apps/web
COPY packages/shared ./packages/shared

# build 前 echo 确认 NEXT_PUBLIC_API_URL 被注入(部署排错用 · 看不到就是 args 没传)
RUN echo "[build] NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL"

# ── ADR 0031 DP3 · Next.js .next/cache BuildKit cache mount ──
# 路径绝对 · 必须跟 next build 写入的 .next/cache 一致(/repo/apps/web/.next/cache)
# 增量编译(webpack/swc cache · 文件级 hash 复用)· sharing=locked 串行写
# 预期:rebuild 时 next build 4-5min → 1-2min(.next/cache 命中)
# ★构建内存护栏(deploy-build-memory-wall · 批0 翻车修):cap next build 主进程 V8 堆 →
#   构建产物膨胀 / 内存跑飞时 next build 干净报「JavaScript heap out of memory」非零退出 →
#   build 失败 → update.sh ERR trap 回滚、绝不 recreate → 站点留旧容器活着(而非 box thrash
#   整机压满 15min)。值可由 update.sh / compose 传 build-arg NODE_MAX_OLD_SPACE 覆盖。
ARG NODE_MAX_OLD_SPACE=3072
ENV NODE_OPTIONS="--max-old-space-size=${NODE_MAX_OLD_SPACE}"
RUN --mount=type=cache,target=/repo/apps/web/.next/cache,sharing=locked \
    cd apps/web && pnpm build

# === Stage 2: runner ===
FROM node:20-alpine AS runner
WORKDIR /repo

ENV NODE_ENV=production
ENV PORT=3000

RUN corepack enable && corepack prepare pnpm@10.32.1 --activate \
    && apk add --no-cache wget

# 拷构建产物 + 仅 production deps
COPY --from=builder /repo/pnpm-workspace.yaml /repo/pnpm-lock.yaml /repo/package.json /repo/turbo.json ./
COPY --from=builder /repo/apps/web ./apps/web
COPY --from=builder /repo/packages/shared ./packages/shared
COPY --from=builder /repo/node_modules ./node_modules
COPY --from=builder /repo/apps/web/node_modules ./apps/web/node_modules
COPY --from=builder /repo/packages/shared/node_modules ./packages/shared/node_modules

WORKDIR /repo/apps/web

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=10 \
    CMD wget -q --spider http://localhost:3000/ || exit 1

CMD ["pnpm", "start"]
