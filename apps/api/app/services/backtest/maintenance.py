"""回测共享卷维护(P1-4b-2)· 清孤儿 run_dir。纯文件操作 · 不碰 DB / 不 import vibe。

vibe-worker 异常退出(OOM/重启)可能残留没被 persist_outcome 清掉的 run_dir,
盘紧 → 定时清超过 TTL 的孤儿目录,防堆积撑爆共享卷。
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path


def cleanup_stale_run_dirs(root: Path, *, ttl_hours: float) -> int:
    """删 root 下最后修改时间超过 ttl_hours 的子目录(孤儿 run_dir)· 返回删除个数。

    只删目录 · 单个删除失败(权限/竞态)跳过不中断 · root 不存在返回 0。
    """
    if not root.is_dir():
        return 0
    cutoff = time.time() - ttl_hours * 3600.0
    removed = 0
    for child in sorted(root.iterdir()):
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
