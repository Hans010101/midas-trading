"""支付域(Phase 2a · 会员订阅收款)。

🔴 红线:本包【收会员订阅费,非交易】· 绝不 import virtual_trading/engine · 凭证只从 env 读。
开权益走 growth.extend_subscription(source='paid' · 不封顶 · 复用 pro 档额度)。
"""
