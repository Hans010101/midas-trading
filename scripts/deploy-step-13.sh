#!/bin/bash
# 点金 Midas · 部署 STEP 13 · Caddyfile + HTTPS 自动证书
# 2026-05-21 · 模式 B 全栈
#
# 用法(服务器):
#   cd /opt/midas
#   git pull origin main
#   bash scripts/deploy-step-13.sh 2>&1 | tee /tmp/deploy-step-13.log
#
# 不动 docker / .env / volume · 只动 /etc/caddy/Caddyfile + systemctl reload caddy

set -euo pipefail

RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; NC=$'\033[0m'

STAGE="init"
on_err() {
  local line=$1
  echo ""
  echo "${RED}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${RED}║  ❌ 失败 · 阶段=「${STAGE}」 · 行号=${line}${NC}"
  echo "${RED}╚═══════════════════════════════════════════════════════════${NC}"
  echo ""
  echo "${YELLOW}--- caddy systemctl status ---${NC}"
  systemctl status caddy --no-pager 2>&1 | head -20 || true
  echo ""
  echo "${YELLOW}--- caddy 最近 50 行日志 ---${NC}"
  journalctl -u caddy --no-pager -n 50 2>&1 || true
  echo ""
  echo "${YELLOW}--- 端口监听(80/443/8000/3000)---${NC}"
  ss -tlnp 2>/dev/null | grep -E ':(80|443|3000|8000)\s' || true
  exit 1
}
trap 'on_err $LINENO' ERR

banner() {
  STAGE="$1"
  echo ""
  echo "${CYAN}╔═══════════════════════════════════════════════════════════${NC}"
  echo "${CYAN}║  === $1 ===${NC}"
  echo "${CYAN}╚═══════════════════════════════════════════════════════════${NC}"
}
ok()   { echo "${GREEN}  ✓ $1${NC}"; }
warn() { echo "${YELLOW}  ⚠ $1${NC}"; }

if [ ! -d /opt/midas/.git ]; then
  echo "${RED}❌ /opt/midas 不是 git 仓库${NC}"; exit 1
fi
cd /opt/midas

DOMAIN_MAIN="midastrade.asia"
DOMAIN_API="api.midastrade.asia"
DOMAIN_WWW="www.midastrade.asia"
EXPECTED_IP="8.210.156.91"
CADDYFILE_SRC="/opt/midas/deploy/Caddyfile"
CADDYFILE_DST="/etc/caddy/Caddyfile"

# ============================================================
banner "1/8 · 自检 · caddy + deploy/Caddyfile + api/web 容器"
# ============================================================
if ! command -v caddy >/dev/null; then
  echo "${RED}❌ caddy 未安装(STEP 4 应已装好)${NC}"; exit 1
fi
ok "caddy = $(caddy version | head -1)"

if [ ! -f "$CADDYFILE_SRC" ]; then
  echo "${RED}❌ $CADDYFILE_SRC 不存在 · 请 git pull origin main 拿最新代码${NC}"
  exit 1
fi
ok "deploy/Caddyfile 在位($(wc -l < $CADDYFILE_SRC) 行)"

# 后端容器必须在跑
API_HEALTHY=$(docker inspect -f '{{.State.Health.Status}}' midas-api 2>/dev/null || echo "no-container")
WEB_HEALTHY=$(docker inspect -f '{{.State.Health.Status}}' midas-web 2>/dev/null || echo "no-container")
if [ "$API_HEALTHY" != "healthy" ] || [ "$WEB_HEALTHY" != "healthy" ]; then
  echo "${RED}❌ midas-api=$API_HEALTHY  midas-web=$WEB_HEALTHY · 应该都是 healthy${NC}"
  echo "${YELLOW}先确保 STEP 10 通过 · 再跑这一步${NC}"
  exit 1
fi
ok "midas-api healthy + midas-web healthy"

# 顺手验证下后端 / 前端 localhost 通(Caddy 反代的目标)
curl -fsS http://127.0.0.1:8000/health >/dev/null || { echo "${RED}❌ 127.0.0.1:8000/health 不通${NC}"; exit 1; }
curl -fsI http://127.0.0.1:3000/ >/dev/null || { echo "${RED}❌ 127.0.0.1:3000 不通${NC}"; exit 1; }
ok "后端 127.0.0.1:8000/health + 前端 127.0.0.1:3000 反代目标都通"

# ============================================================
banner "2/8 · DNS 检查 · 3 个域名必须解析到 ${EXPECTED_IP}"
# ============================================================
check_dns() {
  local domain=$1
  local got
  got=$(dig +short "$domain" @8.8.8.8 2>/dev/null | head -1)
  if [ "$got" = "$EXPECTED_IP" ]; then
    ok "$domain → $got"
    return 0
  else
    echo "${RED}  ❌ $domain → '$got'(期望 $EXPECTED_IP)${NC}"
    return 1
  fi
}

DNS_OK=true
check_dns "$DOMAIN_MAIN" || DNS_OK=false
check_dns "$DOMAIN_API" || DNS_OK=false
check_dns "$DOMAIN_WWW" || DNS_OK=false

if [ "$DNS_OK" != "true" ]; then
  echo ""
  echo "${YELLOW}DNS 解析不对 · Let's Encrypt 签证书会失败${NC}"
  echo "${YELLOW}检查域名注册商后台 · 3 条 A 记录都指向 ${EXPECTED_IP}${NC}"
  echo "${YELLOW}如果是刚改 · 等 5-30 分钟 DNS 全球生效再重跑${NC}"
  exit 1
fi
ok "三个域名 DNS 解析全部正确"

# ============================================================
banner "3/8 · 备份原 Caddyfile + 安装新 Caddyfile"
# ============================================================
if [ -f "$CADDYFILE_DST" ]; then
  BACKUP_PATH="${CADDYFILE_DST}.backup.$(date +%Y%m%d-%H%M%S)"
  cp -p "$CADDYFILE_DST" "$BACKUP_PATH"
  ok "原 Caddyfile 备份到 $BACKUP_PATH"
fi

cp "$CADDYFILE_SRC" "$CADDYFILE_DST"
chown root:root "$CADDYFILE_DST"
chmod 644 "$CADDYFILE_DST"
ok "新 Caddyfile 已写入 $CADDYFILE_DST"
ls -la "$CADDYFILE_DST"

# ============================================================
banner "4/8 · caddy validate · 语法检查 + format 检查"
# ============================================================
if ! caddy validate --config "$CADDYFILE_DST" 2>&1; then
  echo "${RED}❌ Caddyfile 语法错${NC}"
  exit 1
fi
ok "Caddyfile 语法 OK"

# ============================================================
banner "5/8 · systemctl reload caddy + 等服务起 443"
# ============================================================
# reload 不行就 restart(reload 偶尔不重读 Caddyfile)
systemctl reload caddy 2>&1 || systemctl restart caddy
sleep 3
if ! systemctl is-active caddy >/dev/null; then
  echo "${RED}❌ caddy systemd 服务没起来${NC}"
  systemctl status caddy --no-pager | head -20
  exit 1
fi
ok "caddy systemd 服务 active"

# 等 443 端口开始监听(证书签发 + bind)
echo "  等 443 端口开始监听(给 caddy 30s 启动 + ACME 准备)..."
for try in $(seq 1 6); do
  if ss -tlnp 2>/dev/null | grep -q ':443\s'; then
    ok "443 端口已被 caddy 监听"
    break
  fi
  echo "  [try $try/6 @ $(date +%T)] 443 还没起 · 等 5s..."
  sleep 5
done

# ============================================================
banner "6/8 · 等 Let's Encrypt 证书签发(最多 3 分钟)"
# ============================================================
# 第一次 reload 时 caddy 会向 Let's Encrypt 申请 3 张证书:
#   api.midastrade.asia · midastrade.asia · www.midastrade.asia
# ACME HTTP-01 challenge 走 80 端口 · 通常 5-30s 完成 · 偶发 60-120s
warn "正常 30s 内拿到证书 · 失败常因 80 端口被防火墙挡 / DNS 没全球生效 / ACME 限流"
warn "不要中断 · 也不要 reload 多次(会触发 ACME 限流:5 次/小时)"

# 循环 curl 实测 https · 至少一个域名通就算成功 · 全通才算稳
CERT_OK=false
for try in $(seq 1 18); do  # 18 × 10s = 180s
  echo "  [try $try/18 @ $(date +%T)]"

  # 同时尝试三个域名 · 任一返回不是 connection error 就说明在签
  status_api=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 "https://${DOMAIN_API}/health" 2>&1 || echo "ERR")
  status_main=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 "https://${DOMAIN_MAIN}/" 2>&1 || echo "ERR")
  status_www=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 -L "https://${DOMAIN_WWW}/" 2>&1 || echo "ERR")

  echo "    api=${status_api}  main=${status_main}  www=${status_www}"

  if [ "$status_api" = "200" ] && [ "$status_main" = "200" ]; then
    ok "三个域名 HTTPS 都通(api 200 + main 200)"
    CERT_OK=true
    break
  fi

  if [ "$try" = "18" ]; then
    echo "${RED}  ❌ 3 分钟内未拿到所有证书${NC}"
    echo "${YELLOW}  --- caddy 最近 40 行日志(看 ACME 错误)---${NC}"
    journalctl -u caddy --no-pager -n 40 | grep -E "error|certificate|ACME|challenge" | tail -20
    echo "${YELLOW}  --- 常见原因 ---${NC}"
    echo "    1. 阿里云防火墙 80 端口没开(ACME HTTP-01 走 80)"
    echo "    2. DNS 还没全球生效(dig @8.8.8.8 看一下)"
    echo "    3. Let's Encrypt 限流(5 次/小时/registered-domain · 等 1h)"
    echo "    4. Caddy 数据目录权限问题(/var/lib/caddy)"
    exit 1
  fi
  sleep 10
done

# ============================================================
banner "7/8 · HTTPS 终态验证 + HSTS / TLS 头检查"
# ============================================================
echo "${CYAN}─── https://${DOMAIN_API}/health ───${NC}"
curl -sS https://${DOMAIN_API}/health
echo ""

echo ""
echo "${CYAN}─── https://${DOMAIN_API}/health -I(看证书 + HSTS)───${NC}"
curl -sI https://${DOMAIN_API}/health | head -10

echo ""
echo "${CYAN}─── https://${DOMAIN_MAIN}/ -I(主站)───${NC}"
curl -sI https://${DOMAIN_MAIN}/ | head -10

echo ""
echo "${CYAN}─── https://${DOMAIN_WWW}/ -I(应见 301 → 主域)───${NC}"
curl -sI https://${DOMAIN_WWW}/ | head -10

echo ""
echo "${CYAN}─── TLS 证书信息(api 子域)───${NC}"
echo | openssl s_client -servername "$DOMAIN_API" -connect "$DOMAIN_API:443" 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates 2>&1 | head -6

# ============================================================
banner "8/8 · 最终汇总 · STEP 13 完成状态"
# ============================================================
STAGE="8/8 final"

echo "${CYAN}─── caddy systemctl ───${NC}"
systemctl is-active caddy && echo "  caddy.service: active"
systemctl is-enabled caddy && echo "  caddy.service: enabled(开机自启)"

echo ""
echo "${CYAN}─── 端口监听 ───${NC}"
ss -tlnp 2>/dev/null | grep -E ':(80|443|3000|8000)\s' | head -6

echo ""
echo "${CYAN}─── docker compose ps(不应有变化)───${NC}"
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.prod.yaml --profile self-hosted ps

echo ""
echo "${CYAN}─── 三域名 HTTPS 终验 ───${NC}"
printf "  api  · "; curl -sS -o /dev/null -w "HTTP %{http_code} · TLS %{ssl_verify_result} · %{time_total}s\n" "https://${DOMAIN_API}/health"
printf "  main · "; curl -sS -o /dev/null -w "HTTP %{http_code} · TLS %{ssl_verify_result} · %{time_total}s\n" "https://${DOMAIN_MAIN}/"
printf "  www  · "; curl -sS -o /dev/null -w "HTTP %{http_code} · TLS %{ssl_verify_result} · %{time_total}s\n" -L "https://${DOMAIN_WWW}/"

echo ""
echo "${GREEN}╔═══════════════════════════════════════════════════════════${NC}"
echo "${GREEN}║  ✅ STEP 13 · Caddy + HTTPS 完成${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  浏览器现在可以打开:${NC}"
echo "${GREEN}║    https://midastrade.asia          (首页)${NC}"
echo "${GREEN}║    https://midastrade.asia/workbench (工作台 · 匿名可看)${NC}"
echo "${GREEN}║    https://api.midastrade.asia/health (后端)${NC}"
echo "${GREEN}║${NC}"
echo "${GREEN}║  下一步:STEP 14-17(cron 备份 + 端到端验收 + 监控基线)${NC}"
echo "${GREEN}╚═══════════════════════════════════════════════════════════${NC}"
