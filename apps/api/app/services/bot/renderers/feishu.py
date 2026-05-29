"""ReplyModel → 飞书交互卡片(interactive card)· ADR 0032 阶段三。

把通道中立 ReplyModel 渲染成飞书 message card JSON:
- title/badge → card header(中国红模板)· 正文 → lark_md div · 免责 → note
- 按钮(Button.action)→ card button,value={"action": action};点击触发 card.action.trigger,
  webhook 取出 action 再进 handle_inbound(逻辑与 TG 共用一份)。URL 按钮(K 线深链)→ url button。

待产品确认(阶段四卡片打磨时再定):
- header 用 "red" 模板(近中国红 #C8102E,飞书 header template 是命名枚举,精确色需自定义卡片 2.0)。
- 按钮点击后【发新卡片】(非原地刷新);TG 是 editMessageText 原地刷新 —— 阶段三飞书先发新消息,
  原地更新(card callback 返回新卡)留阶段四统一做。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.bot.replies import _BRAND

if TYPE_CHECKING:
    from app.services.bot.replies import Button, ReplyModel

_HEADER_TEMPLATE = "red"  # 近中国红 · 待产品确认(见模块 docstring)


def _header_text(reply: ReplyModel) -> str:
    if reply.title is None:
        return _BRAND
    return f"{_BRAND} · {reply.title}{reply.badge}"


def _button_element(btn: Button) -> dict[str, Any]:
    el: dict[str, Any] = {
        "tag": "button",
        "text": {"tag": "plain_text", "content": btn.label},
        "type": "default",
    }
    if btn.url is not None:
        el["url"] = btn.url
    else:
        # 回调按钮:value 携带 action,点击触发 card.action.trigger
        el["value"] = {"action": btn.action if btn.action is not None else ""}
    return el


def render_for_feishu(reply: ReplyModel) -> dict[str, Any]:
    """ReplyModel → 飞书 interactive card(dict)· feishu_client.send_card 序列化发出。"""
    elements: list[dict[str, Any]] = []

    # 正文(prerendered 成稿也直接放正文 · 阶段三只读不产生成稿,这里只做兜底)
    if reply.text:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": reply.text}})

    # 按钮:每行一个 action 模块(保留 ReplyModel 的行分组)
    for row in reply.buttons:
        if not row:
            continue
        elements.append({
            "tag": "action",
            "actions": [_button_element(b) for b in row],
        })

    # 免责声明 · 放卡片底部 note 元素
    if reply.disclaimer is not None:
        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": reply.disclaimer}],
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": _HEADER_TEMPLATE,
            "title": {"tag": "plain_text", "content": _header_text(reply)},
        },
        "elements": elements,
    }
