"""AI 决策卡服务包 · 0012 ADR。

模块组成:
  - llm.py        · LiteLLM 包装 + mock 模式 toggle(0012 § LiteLLM 接入)
  - indicators.py · MA/MACD/RSI/BOLL 纯 Python 实现
  - cache.py      · Redis 应用层缓存(0012 § 应用层结果缓存)
  - validator.py  · 祈使句 → 陈述句 改写(0012 红线 ②)
  - usage.py      · ai_usage_log 写入 helper
  - agents/       · 技术面 Agent(M1 二波单 Agent · 0012 § M1 二波降级 v2)
  - workflow.py   · LangGraph 6 节点 workflow
"""
