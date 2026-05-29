"""ReplyModel → Telegram 原生(Markdown text + inline_keyboard)· ADR 0032 阶段一。

唯一职责:把通道中立的 ReplyModel 渲染成 Telegram 专属的 BotReply —— 品牌头(*粗体*)、
徽章、免责尾(_斜体_)、inline_keyboard JSON 全部在这里拼。

🔴 零回归契约(ADR 0032 §3):render_for_telegram(build_X(...)) 必须与重构前
telegram_ui.render_X(...) 字节级一致(text)+ 结构一致(keyboard)· 见 test_bot_golden.py。
callback_data 命名空间冻结(= ReplyModel.Button.action),历史按钮 / router 分支不受影响。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.bot.replies import _BRAND

if TYPE_CHECKING:
    from app.services.bot.replies import Button, ReplyModel

Keyboard = dict[str, list[list[dict[str, str]]]]


@dataclass(frozen=True)
class BotReply:
    """一次 Telegram 响应 · text(Markdown)+ 可选 inline 键盘(transport 发送用)。"""

    text: str
    keyboard: Keyboard | None = None


def _to_keyboard(buttons: tuple[tuple[Button, ...], ...]) -> Keyboard | None:
    if not buttons:
        return None
    rows: list[list[dict[str, str]]] = []
    for row in buttons:
        out_row: list[dict[str, str]] = []
        for b in row:
            cell: dict[str, str] = {"text": b.label}
            if b.url is not None:
                cell["url"] = b.url
            else:
                cell["callback_data"] = b.action if b.action is not None else ""
            out_row.append(cell)
        rows.append(out_row)
    return {"inline_keyboard": rows}


def render_for_telegram(reply: ReplyModel) -> BotReply:
    """ReplyModel → BotReply(Telegram 成稿)。

    - prerendered:text 已是完整成稿(成交回执)· 不加品牌头 / 不加免责尾。
    - 否则:`*{品牌}*` 或 `*{品牌} · {title}*` + badge + `\n\n` + text;disclaimer 非空则
      追加 `\n\n_{disclaimer}_`。
    """
    if reply.prerendered:
        text = reply.text
    else:
        title = reply.title
        header = f"*{_BRAND}*" if title is None else f"*{_BRAND} · {title}*"
        header += reply.badge
        text = f"{header}\n\n{reply.text}"
    if reply.disclaimer is not None:
        text = f"{text}\n\n_{reply.disclaimer}_"
    return BotReply(text=text, keyboard=_to_keyboard(reply.buttons))
