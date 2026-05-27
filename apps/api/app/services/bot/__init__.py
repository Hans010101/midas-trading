"""Bot 核心层 + Telegram 适配层 · 0025 M1-G G3。

分层(对齐 0025 §2.2):
- 核心层(平台无关 · 只认 user_id / 结构化数据):
    · identity.py · chat_id → user_id 解析(唯一鉴权边界 · R1)
    · query.py    · symbol / watchlist / positions → 结构化结果(只读 CH+PG)
- Telegram 适配层(平台特定 · 字符串 / 按钮 / 会话态):
    · telegram_ui.py · inline 键盘 + 渲染 + BotReply
    · session.py     · 多步会话态(Redis · DP7)
    · router.py      · 入站命令 / 回调编排

红线:bot 一切输出带「仅供参考,不构成投资建议」· 行情只读已采数据、不打实时上游。
"""
