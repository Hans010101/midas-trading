"""Pytest 全局 fixtures。

在导入 app.* 之前注入测试用环境变量,避免 Settings() 因缺 SECRET_KEY 报错。
conftest.py 由 pytest 在收集测试前最先加载,这里设置的 env 对后续导入生效。
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://midas:midas_dev@localhost:5432/midas_test",
)
