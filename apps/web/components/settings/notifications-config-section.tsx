'use client'

/**
 * 设置页 · 消息推送配置 section(段 1 补丁 B 留 placeholder)。
 *
 * 段 2 Task 6 填充实际 UI(飞书 webhook / TG bot token + chat_id / 测试按钮)。
 */

export function NotificationsConfigSection() {
  return (
    <section className="mb-6 rounded-lg border border-dashed border-paper bg-cream/40 p-5">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="font-serif text-lg font-bold text-muted-foreground/70">
          消息推送
        </h2>
        <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          段 2 Task 6 填充
        </span>
      </div>
      <p className="text-xs text-muted-foreground/70">
        飞书机器人 / Telegram bot · 成交通知 · 价格异动 · 测试按钮
      </p>
    </section>
  )
}
