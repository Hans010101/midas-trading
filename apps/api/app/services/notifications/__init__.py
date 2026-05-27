"""推送通知服务 · 0009 设计 → 0025 G2a 统一 Telegram bot。

核心层(平台无关):
- events.py · NotificationEvent dataclass tree(「发什么」)
- dispatcher.py · 按用户 config 编排派发(「给谁 / 走哪些通道」)

适配层(平台特定):
- adapters/telegram.py · 渲染 + 经统一 bot 发送(「Telegram 怎么发」)
- telegram.py · TG bot HTTP client(sendMessage / setWebhook)
- templates.py · TG markdown 文案渲染

(0025 G2a 已移除飞书:旧 feishu.py 删除、per-user token 下线。)
"""
