"""Bot 核心层 + 通道中立 / 适配层 · 0025 M1-G G3 + ADR 0032 多通道地基。

分层(对齐 0025 §2.2 + ADR 0032):
- 核心层(平台无关 · 只认 user_id / 结构化数据):
    · identity.py · (channel, channel_uid) → user_id 解析(唯一鉴权边界 · R1)
    · query.py    · symbol / watchlist / positions → 结构化结果(只读 CH+PG)
    · order.py    · 下单 facade(撮合编排 · 无通道字符串)
- 通道中立层(ADR 0032):
    · replies.py  · ReplyModel / InboundMessage / Button + build_*(无通道格式)
    · router.py   · handle_inbound(InboundMessage)->ReplyModel 编排
    · session.py  · 多步会话态(Redis · DP7)
- 通道 renderer / 适配(平台特定 · 字符串 / 按钮):
    · renderers/telegram.py · ReplyModel → Telegram BotReply;router.handle_command/
      handle_callback 为 TG 适配入口(飞书 P3 另起 renderer + webhook)

红线:bot 一切输出带「仅供参考,不构成投资建议」· 行情只读已采数据、不打实时上游。
"""
