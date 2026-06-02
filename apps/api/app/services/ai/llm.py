"""LiteLLM 统一调用层 · 0012 ADR § LiteLLM 接入。

为什么用 LiteLLM 而不是直接 DeepSeek SDK:
  - 切换模型零成本(改 env LLM_MODEL 即可)
  - 自带 retry / timeout / token tracking
  - 跨厂商统一 OpenAI 风格 API

mock 模式(M1 二波等 key 时):
  - 当 settings.deepseek_api_key 为空 OR settings.llm_mock_mode=True
  - 返回固定假分析 JSON · workflow 端到端可跑
  - 等产品负责人填 DEEPSEEK_API_KEY 后,is_mock_mode() 自动返回 False · 走真实调用
  - mock 和真实调用接口签名一致 · 无侵入切换

红线遵守:
  - retry 只在 transport 层(LiteLLM 内部)· 不在上层叠加(铁律 P5)
  - max_tokens 默认 1024(0012 § 硬上限)
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


# ===== 公共接口 =====


@dataclass(frozen=True)
class LLMResponse:
    """LLM 调用返回 · content + 用量元信息。"""
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    is_mock: bool


def is_mock_mode() -> bool:
    """是否使用 mock LLM。

    两种情况走 mock:
      1. settings.llm_mock_mode 显式 True(测试用)
      2. settings.deepseek_api_key 为空(产品负责人还没填 key)

    产品负责人填了 .env 中的 DEEPSEEK_API_KEY 后,此函数自动返回 False,
    is_mock 字段切换到 real,无需改任何代码。
    """
    if settings.llm_mock_mode:
        return True
    return not settings.deepseek_api_key


async def ainvoke(
    prompt: str,
    *,
    system: str = "",
    response_format_json: bool = False,
    max_tokens: int | None = None,
    temperature: float = 0.3,
) -> LLMResponse:
    """异步 LLM 调用 · mock / real 自动切换。

    参数:
      prompt: 用户 prompt 文本
      system: system prompt(可选)
      response_format_json: True 时强制 JSON 输出(对应 DeepSeek JSON mode)
      max_tokens: 默认 settings.llm_max_tokens(1024)
      temperature: 默认 0.3(偏保守,减少瞎说)

    return:
      LLMResponse · is_mock=True 时是 mock 输出,False 是真实调用结果
    """
    max_tokens = max_tokens or settings.llm_max_tokens

    if is_mock_mode():
        return _mock_invoke(prompt, system, response_format_json)

    # ============ 真实 LiteLLM 调用路径 · 生产主路径 ============
    # 当 DEEPSEEK_API_KEY 已配置 · is_mock_mode() 返回 False · 走这里。
    # mock 分支(上方 `if is_mock_mode()`)仅作为 key 缺失时的兜底,确保 UI 仍可运行。
    # 详见 docs/decisions/0012-ai-decision-card.md § M1 二波验收记录
    from litellm import acompletion  # noqa: PLC0415

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    extra: dict[str, Any] = {}
    if response_format_json:
        extra["response_format"] = {"type": "json_object"}

    resp = await acompletion(
        model=settings.llm_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=settings.llm_timeout_seconds,
        num_retries=2,                      # transport 层 retry · 铁律 P5
        api_key=settings.deepseek_api_key,
        **extra,
    )

    content = resp.choices[0].message.content or ""
    usage = resp.usage
    return LLMResponse(
        content=content,
        prompt_tokens=getattr(usage, "prompt_tokens", 0),
        completion_tokens=getattr(usage, "completion_tokens", 0),
        total_tokens=getattr(usage, "total_tokens", 0),
        is_mock=False,
    )


# ===== Mock 实现 =====


# Mock 输出基于市场上下文随机化一点 · 让端到端看起来"真实"
_MOCK_NARRATIVES = [
    (
        "缠论结构显示近期上升笔延伸,中枢上沿突破有效。"
        "MACD 金叉但 RSI 接近超买,短线分歧明显,后续若回踩中枢上沿不破,二买信号成立。"
    ),
    (
        "笔序列出现连续向下,跌破最近中枢下沿。"
        "MACD 死叉走深,RSI 进入超卖区域,从结构看可能孕育底背离,关注下方支撑。"
    ),
    (
        "K 线在中枢内反复震荡,笔的力度收窄。"
        "MA60 横向运行,布林带收口,等待方向选择;盘整阶段建议轻仓观察,不追涨杀跌。"
    ),
    (
        "上升趋势中近期出现回调笔,回踩 MA20 获得支撑,RSI 回到中位。"
        "缠论近期识别到三类买点,符合突破中枢后回踩不破的结构,趋势延续概率较大。"
    ),
]


def _mock_invoke(
    prompt: str, system: str, response_format_json: bool,
) -> LLMResponse:
    """Mock LLM 调用 · 返回固定/半随机假数据 · 端到端测试用。

    is_mock=True 标记 · 调用方(workflow 节点)可以根据这个字段在 UI 上提示
    「当前为离线模式,数据为模拟」(M1 二波先不做这个 UI 提示,默默走)。
    """
    # 简单根据 prompt 内容选 narrative · 让不同标的看起来不一样
    seed = sum(ord(c) for c in prompt[:64])
    rng = random.Random(seed)
    narrative = rng.choice(_MOCK_NARRATIVES)

    if response_format_json:
        # 技术面 Agent 期望的 JSON · 随机化 score 让不同标的不同
        score = rng.randint(-70, 70)
        confidence = round(rng.uniform(0.55, 0.85), 2)
        # 从 prompt 里粗暴抓 last_close 数字给 key_levels
        # M1 二波不追求 mock 精确 · 让 UI 跑通就行
        key_levels = [
            round(rng.uniform(50, 150), 2),
            round(rng.uniform(150, 250), 2),
        ]
        payload = {
            "score": score,
            "confidence": confidence,
            "rationale": narrative,
            "key_levels": key_levels,
        }
        content = json.dumps(payload, ensure_ascii=False)
    else:
        content = narrative

    # 估算 token 数(粗略 · 中文按字符数算)
    prompt_tokens = len(prompt) + len(system)
    completion_tokens = len(content)

    logger.info(
        "[llm.mock] response_format_json=%s tokens≈%d",
        response_format_json, prompt_tokens + completion_tokens,
    )

    return LLMResponse(
        content=content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        is_mock=True,
    )


__all__ = ["LLMResponse", "ainvoke", "is_mock_mode"]
