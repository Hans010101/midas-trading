# 0013 · Compose ports MERGE 陷阱(2026-05-21 部署翻车)

## 状态
Recorded (2026-05-21)

## 事故

模式 B 部署 STEP 10 · `docker compose up -d --build --profile self-hosted` 起 6 服务时,
`midas-api` 容器反复报:

```
failed to bind host port 127.0.0.1:8000/tcp: address already in use
```

但 `ss -tlnup`/`lsof -i :8000`/`iptables -t nat -L` 全部查不到任何进程在占 8000 ·
`systemctl restart docker` + `docker compose down --remove-orphans` 清场后仍冲突。

一次重启 docker 后偶发地不报端口冲突,但 api 容器又改报:
```
ClientConnectorDNSError: Cannot connect to host clickhouse:8123
[Could not contact DNS servers]
```

容器在重试 ports 绑定过程中被丢回 default bridge network 而非 midas-net ·
docker 内部 DNS 找不到 `clickhouse`。

## 根因

**Docker Compose 的 `ports` 字段是 MERGE 合并,不是 REPLACE 替换。**

base `docker-compose.yaml` 给 api 写了:
```yaml
api:
  ports:
    - "8000:8000"          # 暴露到 0.0.0.0:8000
```

prod overlay 想收紧到 localhost · 写成:
```yaml
api:
  ports:                    # ❌ 没标签 = MERGE
    - "127.0.0.1:8000:8000"
```

合并后实际生效是:
```yaml
api:
  ports:
    - "8000:8000"             # base · 没擦
    - "127.0.0.1:8000:8000"   # overlay · 追加
```

第一条占住 0.0.0.0:8000(全 IP)· 第二条试图绑 127.0.0.1:8000 →
**127.0.0.1 是 0.0.0.0 的子集 · 已被自己占** → `address already in use`。

绑定失败发生在 docker 内部 endpoint setup · 从未真正 listen ·
`ss/lsof/iptables` 自然查不到。

## 修复

prod overlay 的 ports **必须**带 `!override` 或 `!reset <new>` 显式替换:

```yaml
api:
  ports: !override
    - "127.0.0.1:8000:8000"

web:
  ports: !override
    - "127.0.0.1:3000:3000"
```

postgres/clickhouse/redis 已经用 `ports: !reset []` 显式清空 · 没踩坑 ·
api/web 是当初写 prod.yaml 时遗漏了。

## 教训

1. **任何 compose overlay 的 `ports` 必须显式 `!override` 或 `!reset`** ·
   不能依赖「写一次会覆盖」的直觉。compose 的列表类字段(ports/volumes/
   environment 数组形式/networks/devices)默认全是 MERGE。
2. **debug 思路:** `ss/lsof/iptables` 查不到的「端口占用」 · 99% 是
   docker 内部配置矛盾 · 不是真实外部占用。`docker compose config`
   可以提前看到 merge 后的实际配置。
3. **重启 docker 后偶发不冲突** · 是 race condition · 不要被这次「好转」
   误导以为问题随机出现;问题确定性存在,只是绑定顺序有时容错。
4. **DNS 错误是次生伤害** · 端口绑定失败时容器被丢回 default bridge ·
   网络隔离崩塌 · `clickhouse` 这种 docker DNS 名解析自然就失败。
   修了根因(ports),DNS 问题会一起消失。

## 防御性补丁(M2 可加)

CI 跑 `docker compose -f docker-compose.yaml -f docker-compose.prod.yaml config | grep -A2 "ports:"` ·
检查每个 service 的 ports 是不是预期数量。当前手动加 `!override` 是最小修复。
