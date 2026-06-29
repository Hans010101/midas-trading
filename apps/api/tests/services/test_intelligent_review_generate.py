"""智能交易复盘 · 生成/发送集成测(需 PG · 本地 collect · CI 真跑)。

PR-8:验 generate_review 存表 + ★幂等覆盖 + dispatch 发 admin(邮件+TG)+ 🔴免责红线 + cleanup。
★mock ainvoke/send_email/telegram.send 均 async(grep-refs 第6坑:被 await 的 mock 必 async)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligent_review import IntelligentReview
from app.models.notification import NotificationConfig
from app.services.ai.llm import LLMResponse
from app.services.virtual_trading.intelligent import review_report as rr
from app.services.visit_stats import CN_TZ
from tests.factories import make_user


def _fake_ainvoke(content: str, *, is_mock: bool = False):  # noqa: ANN202
    """★async mock(被 await → 必 async · 第6坑)· 返 LLMResponse。"""
    async def _f(**_kwargs: object) -> LLMResponse:
        return LLMResponse(
            content=content, prompt_tokens=100, completion_tokens=200,
            total_tokens=300, is_mock=is_mock,
        )
    return _f


_NOW = datetime(2026, 6, 29, 20, 0, tzinfo=CN_TZ)


@pytest.mark.asyncio
async def test_generate_persists(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rr, "ainvoke", _fake_ainvoke("复盘:整体胜率28.8%·盈亏比0.52", is_mock=False))
    review = await rr.generate_review(db_session, "day", _NOW)
    assert review.period == "day"
    assert review.period_start == date(2026, 6, 29)
    assert "胜率28.8%" in review.content
    assert review.is_mock is False
    assert review.total_tokens == 300


@pytest.mark.asyncio
async def test_generate_idempotent(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    # ★同 period + period_start 重跑 → 覆盖(唯一约束)· 不产生重复行
    monkeypatch.setattr(rr, "ainvoke", _fake_ainvoke("v1"))
    await rr.generate_review(db_session, "day", _NOW)
    monkeypatch.setattr(rr, "ainvoke", _fake_ainvoke("v2"))
    r2 = await rr.generate_review(db_session, "day", _NOW)
    cnt = await db_session.scalar(
        select(func.count()).select_from(IntelligentReview).where(
            IntelligentReview.period == "day",
            IntelligentReview.period_start == date(2026, 6, 29),
        ),
    )
    assert cnt == 1                 # 幂等:覆盖非新增
    assert r2.content == "v2"       # 内容已更新


@pytest.mark.asyncio
async def test_dispatch_sends_admin_with_disclaimer(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await make_user(db_session, role="admin")
    db_session.add(NotificationConfig(user_id=admin.id, tg_chat_id="12345"))
    await db_session.commit()

    monkeypatch.setattr(rr, "ainvoke", _fake_ainvoke("复盘正文示例"))
    captured: dict[str, str] = {}

    async def _fake_email(*, to: str, html: str, **_kw: object) -> None:
        captured["email_to"] = to
        captured["html"] = html

    async def _fake_tg(_token: str, chat_id: str, text: str, **_kw: object) -> dict:
        captured["tg_chat"] = chat_id
        captured["tg_text"] = text
        return {}

    monkeypatch.setattr(rr, "send_email", _fake_email)
    monkeypatch.setattr(rr.telegram, "send", _fake_tg)
    monkeypatch.setattr(rr.settings, "tg_bot_token", "test-token")

    result = await rr.dispatch_review(db_session, "day", _NOW, channels={"email", "tg"})
    assert result["sent"]["email"] == 1
    assert result["sent"]["tg"] == 1
    assert captured["email_to"] == admin.email
    assert captured["tg_chat"] == "12345"
    # 🔴AI 输出免责红线(email + TG 双通道)
    assert "不构成投资建议" in captured["html"]
    assert "不构成投资建议" in captured["tg_text"]


@pytest.mark.asyncio
async def test_dispatch_email_only_for_weekly(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 周报只邮件(无 TG channel)
    await make_user(db_session, role="admin")
    monkeypatch.setattr(rr, "ainvoke", _fake_ainvoke("周报正文"))
    calls = {"email": 0, "tg": 0}

    async def _fake_email(**_kw: object) -> None:
        calls["email"] += 1

    async def _fake_tg(*_a: object, **_kw: object) -> dict:
        calls["tg"] += 1
        return {}

    monkeypatch.setattr(rr, "send_email", _fake_email)
    monkeypatch.setattr(rr.telegram, "send", _fake_tg)
    result = await rr.dispatch_review(db_session, "week", _NOW, channels={"email"})
    assert result["sent"]["email"] == 1
    assert calls["tg"] == 0  # 周报不发 TG


@pytest.mark.asyncio
async def test_cleanup_old_reviews(db_session: AsyncSession) -> None:
    db_session.add(IntelligentReview(
        period="week", period_start=date(2026, 1, 1), trade_count=0,
        content="老复盘", review_data={}, is_mock=True, total_tokens=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),  # 远超 30 天
    ))
    await db_session.commit()
    deleted = await rr.cleanup_old_reviews(db_session, datetime(2026, 6, 29, tzinfo=UTC))
    assert deleted >= 1
