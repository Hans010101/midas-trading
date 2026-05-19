# 点金 Midas · web 多阶段构建
# 构建上下文:仓库根目录(..)
# 构建命令:docker build -f apps/web/Dockerfile -t midas-web ..

# === Stage 1: builder ===
FROM node:20-alpine AS builder
WORKDIR /repo

RUN corepack enable && corepack prepare pnpm@10.32.1 --activate

# 先拷 manifest 利用 Docker 层缓存
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json turbo.json ./
COPY apps/web/package.json ./apps/web/
COPY packages/shared/package.json ./packages/shared/

RUN pnpm install --frozen-lockfile

# 拷 web + 共享包源码
COPY apps/web ./apps/web
COPY packages/shared ./packages/shared

RUN cd apps/web && pnpm build

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
