"""虚拟交易服务层 · 0008 v2 三独立子账户。

- fees · 滑点 + 手续费 表 + 计算 helper
- engine · 市价单撮合(原子 SQL,无 FX,纯 SQL 原子语义)
- equity · 单市场快照 + 多市场 portfolio 聚合
"""
