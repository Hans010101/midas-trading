"""训练营文章目录(slug → 阶)· 后端单一事实源,镜像前端 manifest.ts ACADEMY_ARTICLES。

🔴 进度端点用它:① 校验 article_slug 合法(只接受已知文章 · 防乱传脏数据);
   ② 派生文章所属 stage(不信前端传);③ 各阶文章总数(进度 X/Y 的 Y)。
★ 同步纪律:训练营加文章(manifest.ts)时必须同步本表(否则新文章无法标记学完)·
   tests/services/test_academy_catalog.py 钉死总数 + 各阶分布,防漏同步静默偏移。
   本表程序化从 manifest 提取生成(勿手敲)。
"""

from __future__ import annotations

# 阶顺序(与 manifest.ts ACADEMY_STAGES 一致)
STAGE_ORDER: tuple[str, ...] = (
    "basics",
    "technical",
    "chan",
    "contract",
    "strategy",
    "system",
)

# slug → stage(镜像 manifest ACADEMY_ARTICLES · 117 篇 · 程序化生成)
ARTICLE_STAGE: dict[str, str] = {
    "A2": "basics",
    "A3": "basics",
    "A4": "basics",
    "A5": "basics",
    "A6": "basics",
    "A7": "basics",
    "A8": "basics",
    "A9": "basics",
    "A10": "basics",
    "A11": "basics",
    "A12": "basics",
    "B1": "technical",
    "B2": "technical",
    "B3": "technical",
    "B4": "technical",
    "B5": "technical",
    "B6": "technical",
    "B7": "technical",
    "B8": "technical",
    "B9": "technical",
    "C1": "chan",
    "C2": "chan",
    "C3": "chan",
    "C4": "chan",
    "C5": "chan",
    "C6": "chan",
    "C7": "chan",
    "C8": "chan",
    "C9": "chan",
    "C1-1": "chan",
    "C1-2": "chan",
    "C1-3": "chan",
    "C1-4": "chan",
    "C1-5": "chan",
    "C1-6": "chan",
    "C1-7": "chan",
    "C1-8": "chan",
    "C1-9": "chan",
    "C1-10": "chan",
    "C1-11": "chan",
    "C1-12": "chan",
    "C1-13": "chan",
    "C1-14": "chan",
    "C1-15": "chan",
    "C1-16": "chan",
    "C1-17": "chan",
    "C1-18": "chan",
    "C1-19": "chan",
    "C1-20": "chan",
    "E1": "contract",
    "E2": "contract",
    "E3": "contract",
    "E4": "contract",
    "E5": "contract",
    "E6": "contract",
    "E7": "contract",
    "E8": "contract",
    "E9": "contract",
    "E10": "contract",
    "C2-1": "contract",
    "C2-2": "contract",
    "C2-3": "contract",
    "C2-4": "contract",
    "C2-5": "contract",
    "C2-6": "contract",
    "C2-7": "contract",
    "C2-8": "contract",
    "C2-9": "contract",
    "C2-10": "contract",
    "C3-1": "strategy",
    "C3-2": "strategy",
    "C3-3": "strategy",
    "C3-4": "strategy",
    "C3-5": "strategy",
    "C3-6": "strategy",
    "C3-7": "strategy",
    "C3-8": "strategy",
    "C3-9": "strategy",
    "C3-10": "strategy",
    "F1": "system",
    "F2": "system",
    "F3": "system",
    "F4": "system",
    "F5": "system",
    "F6": "system",
    "F7": "system",
    "F8": "system",
    "F9": "system",
    "F10": "system",
    "F11": "system",
    "F12": "system",
    "F13": "system",
    "F14": "system",
    "F15": "system",
    "F16": "system",
    "F17": "system",
    "F18": "system",
    "F19": "system",
    "F20": "system",
    "F21": "system",
    "F22": "system",
    "F23": "system",
    "F24": "system",
    "F25": "system",
    "F26": "system",
    "F27": "system",
    "F28": "system",
    "F29": "system",
    "F30": "system",
    "F31": "system",
    "F32": "system",
    "F33": "system",
    "F34": "system",
    "F35": "system",
    "F36": "system",
    "F37": "system",
    "F38": "system",
}

# 合法 slug 集(校验用 · O(1) 查)
ACADEMY_ARTICLE_SLUGS: frozenset[str] = frozenset(ARTICLE_STAGE)

# 各阶文章总数(进度 X/Y 的 Y · 派生 · 保持 STAGE_ORDER 顺序)
STAGE_TOTALS: dict[str, int] = {
    stage: sum(1 for s in ARTICLE_STAGE.values() if s == stage) for stage in STAGE_ORDER
}


def is_valid_slug(slug: str) -> bool:
    """slug 是否为已知训练营文章(进度端点校验 · 防乱传脏数据)。"""
    return slug in ACADEMY_ARTICLE_SLUGS


def stage_of(slug: str) -> str | None:
    """文章所属阶(不信前端传 · 服务端从目录派生);未知 slug → None。"""
    return ARTICLE_STAGE.get(slug)
