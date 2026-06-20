"""标准化市场周报服务(P1/P2 第一刀)。

- generate.py:聚合四市场现成快照 → 占位 prompt 调 AI → 强制免责 → 存 draft。
- store.py:admin 复核 CRUD(列表 / 取单 / 编辑 / 批准)。
"""
