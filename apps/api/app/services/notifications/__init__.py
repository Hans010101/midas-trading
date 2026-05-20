"""推送通知服务 · 0009 设计。

- events.py · NotificationEvent dataclass tree
- templates.py · 飞书 card / TG markdown 文案渲染
- feishu.py · 飞书自定义机器人 client(关键词 "点金")
- telegram.py · TG bot sendMessage client
- dispatcher.py · 按用户 config 派发到 0~2 个通道
"""
