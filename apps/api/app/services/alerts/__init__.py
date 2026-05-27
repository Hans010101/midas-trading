"""告警规则引擎 · 0025 G2b。

- registry.py · 指标注册表(每指标:元信息 + 读 ClickHouse 取最新值的 fetcher)
- engine.py   · 规则求值(取值 → 算子比阈值)

扫描 worker(apps/worker/tasks/alert_scan.py)周期遍历启用规则 → engine 求值 →
命中经 G2a 核心层 dispatch 推送。所有取值只读 ClickHouse 已采数据,不打实时上游。
"""
