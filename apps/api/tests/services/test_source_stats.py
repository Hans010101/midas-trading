"""SEO 批6 · 来源归因纯函数 classify_source 全矩阵(无 IO · 本地秒级真跑)。

★这是 GEO 归因的核心红线:AI 引擎必须优先于搜索命中(gemini.google 归 gemini 非 google)·
  utm 优先于 referrer · direct/referral 兜底 · 大小写/www./端口归一。桶集合有界。
record_*/端点/flush 落库测走 tests/api/test_source_stats_api.py(需真 Redis/PG · CI 真跑)。
"""

from __future__ import annotations

import pytest

from app.services.visit_stats import classify_source


@pytest.mark.parametrize(
    ("ref_host", "utm", "expect"),
    [
        # ── AI 引擎(★必须优先于搜索:gemini.google.com 含 google. 但归 gemini)──
        ("chat.openai.com", None, "chatgpt"),
        ("www.chatgpt.com", None, "chatgpt"),
        ("www.perplexity.ai", None, "perplexity"),
        ("gemini.google.com", None, "gemini"),
        ("bard.google.com", None, "gemini"),
        ("copilot.microsoft.com", None, "copilot"),
        ("claude.ai", None, "claude"),
        ("kimi.moonshot.cn", None, "kimi"),
        ("www.doubao.com", None, "doubao"),
        ("metaso.cn", None, "metaso"),
        # ── 搜索引擎 ──
        ("www.google.com", None, "google"),
        ("google.com.hk", None, "google"),
        ("www.bing.com", None, "bing"),
        ("m.baidu.com", None, "baidu"),
        ("duckduckgo.com", None, "duckduckgo"),
        ("yandex.ru", None, "yandex"),
        ("www.sogou.com", None, "sogou"),
        # ── 社交 / IM ──
        ("t.co", None, "x"),
        ("twitter.com", None, "x"),
        ("x.com", None, "x"),
        ("t.me", None, "telegram"),
        ("www.facebook.com", None, "facebook"),
        ("www.reddit.com", None, "reddit"),
        # ── utm 优先于 referrer(即使 referrer 是搜索)──
        ("www.google.com", "newsletter", "newsletter"),
        (None, "chatgpt", "chatgpt"),
        (None, "TG", "telegram"),                 # 大小写 + 别名归一
        (None, "some_campaign_x", "utm:other"),   # 非白名单 → utm:other(防爆炸)
        # ── direct / referral 兜底 ──
        (None, None, "direct"),
        ("", None, "direct"),
        ("   ", None, "direct"),
        ("some-random-blog.com", None, "referral"),
        # ── 归一:大小写 / www. / 端口 ──
        ("WWW.GOOGLE.COM", None, "google"),
        ("google.com:443", None, "google"),
    ],
)
def test_classify_source_matrix(ref_host: str | None, utm: str | None, expect: str) -> None:
    assert classify_source(ref_host, utm) == expect


def test_classify_source_ai_beats_search_ordering() -> None:
    """★回归钉死:AI 规则必须在搜索之前命中(gemini.google / copilot.microsoft)。"""
    assert classify_source("gemini.google.com") == "gemini"
    assert classify_source("copilot.microsoft.com") == "copilot"
    # 而纯 google 搜索仍归 google(不被 gemini 误吞)
    assert classify_source("www.google.com") == "google"


def test_classify_source_bucket_set_bounded() -> None:
    """桶集合有界:任意随机 host / 未知 utm 只落到固定兜底桶(防看板维度爆炸)。"""
    assert classify_source("totally-unknown-domain-xyz.io") == "referral"
    assert classify_source(None, "weird-source-name") == "utm:other"
    assert classify_source(None, None) == "direct"


def test_classify_source_self_host_internal() -> None:
    """★Bug A 纵深防御:同域(自有公网域)ref_host 归 internal · 不误记 referral。

    2026-07-07 流量归因诊断:站内跳转的同域 referrer 曾被误判成外部 referral、污染来源桶。
    前端 extractRefHost 已用 Host 头剔自指,这是后端兜底(前端漏发时仍归 internal)。
    """
    self_host = "midastrade.asia"
    # 同域(含 www / 端口不对称)→ internal
    assert classify_source("midastrade.asia", None, self_host=self_host) == "internal"
    assert classify_source("www.midastrade.asia", None, self_host=self_host) == "internal"
    assert classify_source("midastrade.asia:443", None, self_host=self_host) == "internal"
    assert classify_source("midastrade.asia", None, self_host="www.midastrade.asia") == "internal"
    # 外部域不受影响:仍按规则表归类(不因传了 self_host 就误伤)
    assert classify_source("www.google.com", None, self_host=self_host) == "google"
    assert classify_source("some-blog.com", None, self_host=self_host) == "referral"
    # utm 优先级仍高于 internal(投放显式来源可信)
    assert classify_source("midastrade.asia", "newsletter", self_host=self_host) == "newsletter"
    # self_host 缺省(None)→ 老行为不变(同域仍归 referral · 向后兼容)
    assert classify_source("midastrade.asia", None) == "referral"
