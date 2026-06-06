"""块4b 共享卷清理单测 · cleanup_stale_run_dirs(纯文件 · CH-free/PG-free · CI 可跑)。"""
from __future__ import annotations

import os
import time
from pathlib import Path

from app.services.backtest.maintenance import cleanup_stale_run_dirs


def test_cleanup_removes_only_stale(tmp_path: Path) -> None:
    fresh = tmp_path / "run_fresh"
    fresh.mkdir()
    (fresh / "metrics.csv").write_text("x", encoding="utf-8")
    stale = tmp_path / "run_stale"
    stale.mkdir()
    (stale / "metrics.csv").write_text("y", encoding="utf-8")
    # backdate stale 目录 mtime 到 10 小时前
    old = time.time() - 10 * 3600
    os.utime(stale, (old, old))

    removed = cleanup_stale_run_dirs(tmp_path, ttl_hours=6)
    assert removed == 1
    assert not stale.exists()  # 超 TTL → 删
    assert fresh.exists()  # 新鲜 → 留


def test_cleanup_missing_root(tmp_path: Path) -> None:
    assert cleanup_stale_run_dirs(tmp_path / "does_not_exist", ttl_hours=6) == 0
