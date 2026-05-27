"""通知适配层(0025 core/adapter 架构)。

核心层(dispatcher / events)只产出「给哪个 user 发哪个结构化 event」;
适配层负责「用某个 IM 平台怎么发」(渲染 + 传输)。

本期只有 telegram 适配器(统一官方 bot)。将来加飞书 = 新增 feishu.py
适配器,核心层不动。
"""
