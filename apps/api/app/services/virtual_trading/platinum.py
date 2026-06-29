"""铂金多账户共享 helper(多账户 PR-2)· 查铂金用户(is_platinum)。

铂金 = superadmin 手动设的 is_platinum 标记(PR-1)· 每铂金用户配托管/智能影子账户(PR-2 account.py)。
worker(PR-4 遍历开平)+ 自助端点(PR-5)共用本模块查铂金用户列表。🔴只读 User.is_platinum · 不碰引擎。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.user import User

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


async def get_platinum_user_ids(session: AsyncSession) -> list[UUID]:
    """所有铂金用户(真人)id 列表 · where is_platinum=true。

    ★比订阅查询简单(PR-1 加的 User.is_platinum 字段·superadmin 手动设)。
    PR-4 worker open scan 遍历此列表 → 各自影子账户开仓。空列表 → 无铂金用户可开(全局账户照常)。
    """
    rows = await session.scalars(select(User.id).where(User.is_platinum.is_(True)))
    return list(rows)
