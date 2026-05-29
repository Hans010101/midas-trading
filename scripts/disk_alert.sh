#!/bin/bash
# 点金 Midas · 磁盘用量告警 → Telegram(2026-05-29 磁盘满复盘配套 · 呼应"监控空白"待办)
#
# 根分区使用率超阈值(默认 85%)→ 经统一 bot 发 TG 告警给管理员。
# 与应用栈解耦:纯系统 cron + bash + curl —— 磁盘满导致 worker/celery 卡死时,
# 这个独立脚本仍能发出告警(beat 任务做不到这点)。与 backup_postgres.sh 同套路。
#
# 用法:
#   - 手动:./scripts/disk_alert.sh
#   - cron(★ Hans 配好 alert.env + 手动试跑通过后再挂):
#       */15 * * * *  cd /opt/midas && ./scripts/disk_alert.sh >> /var/log/midas-disk-alert.log 2>&1
#
# 依赖凭证(放 /etc/midas/alert.env · chmod 600 · root 拥有):
#   TG_BOT_TOKEN=...            # 统一 bot 的 token(与线上 bot 同一个)
#   ADMIN_TG_CHAT_ID=...        # 收告警的管理员 chat_id(见下方"如何获取")
#
# 如何获取 ADMIN_TG_CHAT_ID:
#   给 bot 随便发一条消息,然后:
#     curl -s "https://api.telegram.org/bot<TG_BOT_TOKEN>/getUpdates" | grep -o '"chat":{"id":[0-9-]*'
#   取里面的数字即你的 chat_id;或复用你 /start 已绑定的那个 chat_id。
#
# 去抖(防刷屏):首次越阈值发一条告警并落 /tmp/midas-disk-alerted 标记;之后保持越阈值
#   状态时静默(不重复发);使用率回落到阈值以下时,发一条"已恢复"并清标记(下次越阈值再报)。
#
# 试跑验证(不等真满盘):临时把阈值设低,确认能收到 TG:
#     ADMIN_TG_CHAT_ID=<你的> TG_BOT_TOKEN=<token> THRESHOLD=1 ./scripts/disk_alert.sh

set -euo pipefail

# === 配置 ===
THRESHOLD="${THRESHOLD:-85}"          # 使用率告警阈值(%)
MOUNT="${MOUNT:-/}"                   # 监控的挂载点(根分区)
MARKER="${MARKER:-/tmp/midas-disk-alerted}"  # 去抖标记
BRAND="点金 Midas"

# 从安全位置加载凭证(与其它运维脚本同套路)
if [ -f /etc/midas/alert.env ]; then
  # shellcheck disable=SC1091
  source /etc/midas/alert.env
fi

: "${TG_BOT_TOKEN:?未设置 TG_BOT_TOKEN(/etc/midas/alert.env)}"
: "${ADMIN_TG_CHAT_ID:?未设置 ADMIN_TG_CHAT_ID(/etc/midas/alert.env)}"

# === 取根分区使用率(整数 %)===
# GNU df(Ubuntu):--output=pcent 输出 "Use%\n 41%" · tail 取值 · tr 只留数字
USED="$(df --output=pcent "$MOUNT" 2>/dev/null | tail -1 | tr -dc '0-9')"
if [ -z "$USED" ]; then
  echo "[disk-alert] $(date -u +%FT%TZ) 取磁盘使用率失败(df 无输出)· 跳过本轮"
  exit 0   # 取不到值绝不误报,也不阻塞 cron
fi

# === TG 发送(curl · 失败不 set -e 中断)===
send_tg() {
  local text="$1"
  curl -fsS --max-time 15 \
    "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    -d chat_id="${ADMIN_TG_CHAT_ID}" \
    -d parse_mode="Markdown" \
    --data-urlencode "text=${text}" >/dev/null
}

# === 主逻辑:越阈值 / 恢复 · 去抖 ===
if [ "$USED" -ge "$THRESHOLD" ]; then
  if [ -f "$MARKER" ]; then
    echo "[disk-alert] $(date -u +%FT%TZ) ${USED}% ≥ ${THRESHOLD}% · 已告警过 · 静默"
    exit 0
  fi
  detail="$(df -h "$MOUNT" 2>/dev/null | tail -1 || true)"
  text="⚠️ *${BRAND} · 磁盘告警*

根分区 \`${MOUNT}\` 使用率 *${USED}%*(阈值 ${THRESHOLD}%)
\`${detail}\`

建议:\`docker system df\` 看占用 · \`docker builder prune -f --keep-storage 10GB\` 清缓存"
  # 仅发送成功才落标记 → 失败(TG 挂)下轮重试,不漏告警
  if send_tg "$text"; then
    touch "$MARKER"
    echo "[disk-alert] $(date -u +%FT%TZ) 已告警 ${USED}% · 落标记"
  else
    echo "[disk-alert] $(date -u +%FT%TZ) ${USED}% 告警发送失败 · 不落标记 · 下轮重试"
  fi
else
  # 已恢复:之前告警过 → 发一条恢复通知并清标记(复位 · 下次越阈值再报)
  if [ -f "$MARKER" ]; then
    text="✅ *${BRAND} · 磁盘恢复*

根分区 \`${MOUNT}\` 已回落至 *${USED}%*(阈值 ${THRESHOLD}% 以下)。"
    send_tg "$text" || echo "[disk-alert] 恢复通知发送失败(不影响复位)"
    rm -f "$MARKER"
    echo "[disk-alert] $(date -u +%FT%TZ) 已恢复 ${USED}% · 清标记"
  else
    echo "[disk-alert] $(date -u +%FT%TZ) ${USED}% < ${THRESHOLD}% · 正常"
  fi
fi
