"""Vibe-trading-ai 回测集成 · 数据源适配(只读 Midas ClickHouse)。

P1-3:MidasCHLoader —— 让 vibe 回测引擎经【路径B】读 Midas 已采进 ClickHouse 的
真实行情跑回测。只读 CH,绝不写;不接 Celery / 前端 / 虚拟下单引擎。
容器化 / 编排是后续 P1-4。
"""
