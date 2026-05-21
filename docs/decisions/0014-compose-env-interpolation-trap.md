# 0014 · Compose .env 插值 + env_file 覆盖 双坑(2026-05-21 部署翻车 #2)

## 状态
Recorded (2026-05-21)

## 事故

模式 B 部署 STEP 10 修了 ports MERGE(0013)后,产品负责人在 `docker compose config`
里发现 api 服务的 DATABASE_URL 拼出来是:

```
DATABASE_URL: postgresql+asyncpg://midas:midas_dev@postgres:5432/midas
```

但 .env 和同份 config 里 POSTGRES_PASSWORD 显示真值 `19e3fa35...`。
密码不一致 → 后续 api 启动会因密码错误连不上 postgres。

Postgres 容器同样被错误密码 init 了(`midas-postgres-data` 卷已经写入了
user `midas` 密码=`midas_dev`)· 必须清卷重 init。

## 根因 · 两个 Compose 机制叠加翻车

### 坑 1 · Compose YAML 插值找不到 .env

Compose 自己的 `${VAR}` 插值(parse-time)默认在 **第一个 `-f` 指定的
compose 文件所在目录** 找 `.env`。

我们的 compose 文件在 `docker/` 目录下,命令是:
```
docker compose -f docker/docker-compose.yaml ...
```

Compose 去 `/opt/midas/docker/` 找 `.env` → 没有 → 所有
`${POSTGRES_PASSWORD:-midas_dev}` 全部回退到 `:-` 后的默认值 `midas_dev`。

注意 · 这跟 `env_file: ../.env` 的路径处理完全是另一码事。
`env_file:` 是 Docker engine 启动时把 .env 加载到容器环境,
路径相对 compose 文件;Compose 的 YAML 插值是另一个独立机制,
找另一个 .env。

### 坑 2 · environment YAML 覆盖 env_file

Compose 文档明确:**`environment:` 块的值会覆盖同名的 `env_file:` 加载的值。**

我们的 base compose 给 api 写了:
```yaml
api:
  env_file:
    - path: ../.env       # 这里加载到 DATABASE_URL=真密码(.env 是对的)
  environment:
    DATABASE_URL: postgresql+asyncpg://...${POSTGRES_PASSWORD:-midas_dev}...
    # ↑ 这里(因为坑 1)插值出来是 midas_dev · 覆盖了 env_file 的真值
```

最终容器拿到的 DATABASE_URL = midas_dev。

Postgres 服务同样:`POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-midas_dev}` 在
environment YAML 里 → 插值失败 → 用 midas_dev 初始化数据卷 → 卷里的
user midas 密码就是 midas_dev,跟 .env / env_file 不一致。

## 修复 · 三层防御

### 1. 删 api / worker 的 YAML `DATABASE_URL` 覆盖

`environment:` 块里不要重新拼装 DATABASE_URL · 让 env_file 直接从 .env 加载:

```yaml
api:
  env_file:
    - path: ../.env
      required: true
  environment:
    # DATABASE_URL 由 env_file 提供 · 不在这里设
    CLICKHOUSE_HOST: clickhouse
    CLICKHOUSE_PORT: "8123"
    ...
```

worker 同样。

### 2. 服务器侧加 symlink · 让 Compose YAML 插值找到 .env

```bash
ln -sf ../.env /opt/midas/docker/.env
```

这一层是给 postgres / clickhouse 的 environment YAML 用的 —— 它们的
`POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-midas_dev}` 必须能正确插值
(image 在 first-start 时按 POSTGRES_PASSWORD env 初始化数据卷)。
不在 YAML 里改 image-required 的 env 变量 · 用 symlink 修通插值即可。

### 3. 清掉被错密码 init 的数据卷

```bash
docker volume rm midas-postgres-data midas-clickhouse-data
```

(只在初次部署阶段做 · 生产数据已经写入后绝不能跑这个)

## 教训

1. **`env_file` 跟 Compose 自己的 `${VAR}` 插值是两个机制,路径规则不同。**
   `env_file:` 看相对 compose 文件位置;插值看 project-directory = 第一个
   compose 文件所在目录(可用 `--env-file` 显式指定)。
2. **`environment:` 覆盖 `env_file:`** —— 在 YAML 里写跟 .env 重复的 key
   是高危行为 · 因为 YAML 的 `${VAR}` 可能因为 .env 找不到而回退到
   `:-default`,反过来覆盖 env_file 里的正确值。
3. **「应用配置型」env 走 env_file;「容器内部 DNS / 通信型」env 走 YAML
   environment 硬编码(`CLICKHOUSE_HOST: clickhouse` 这种 docker 网络名)。**
   两类不要混。
4. **debug 思路:** `docker compose config` 是金标准 —— 看它的输出而不是
   靠脑补 / 看 .env。`docker compose config | grep DATABASE_URL` 一行
   就能发现坑。
5. **image-required env(POSTGRES_PASSWORD / CLICKHOUSE_DB 这种)** 还是
   留在 YAML environment 里 + 用 symlink 让 YAML 插值正常 · 因为这些
   是 image init script 直接读的,得保证它们准确 — 但要确保 Compose
   能找到 .env 来插值。

## 防御性补丁(M2 可加)

- 部署文档 `deployment-runbook.md` STEP 10 前加一步「sanity check」:
  ```bash
  docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml config \
    | grep -E "DATABASE_URL|POSTGRES_PASSWORD|midas_dev" | head -20
  ```
  如果还出现 `midas_dev` · 立即停 · 排查 .env / symlink。
- 加 deploy.sh 包装脚本统一带 `--env-file ../.env` · 不让运维直接跑
  `docker compose` 裸命令。

## 跟 0013 的关系

0013 是 ports MERGE 翻车,0014 是 env 插值 + 覆盖翻车。两个坑都属于
「Compose 默认行为不直观」类。修了 0013 后 docker compose 才能起 ·
但起来后 0014 让数据库认证错。两次连击让 STEP 10 卡了两轮。
