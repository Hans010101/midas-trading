"""模块结业测验题库 + 判分 · 训练营 B 期刀2(题库录入:6 模块 81 题)。

🔴 防作弊红线:正确答案(answer_index)【只在后端】· 前端只拿题干+选项(public_questions),
   提交选项下标后【后端用本表重新判分】(score_exam)· 前端传的分数一律不信。
🔴 纯增量:只读本题库 + 落 academy_exam_result · 不碰交易/支付/会员。

★ 题库来源:Hans 质检通过的 exam_questions.json(本目录 · 6 模块 81 题 · 答案均匀 A/B/C/D)·
   ★数据与代码分离:题+答案存后端 JSON(随 app/ 进镜像 · 绝不入前端 bundle)· exams.py 仅加载 + 判分。
   JSON 字段 question → ExamQuestion.stem(与随堂小测 quizzes.ts 结构一致)。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

# 达标线:答对 ≥ 80%(题数 × 0.8 向上取整 = 及格题数)
PASS_RATIO = 0.8

_QUESTIONS_FILE = Path(__file__).parent / "exam_questions.json"


@dataclass(frozen=True)
class ExamQuestion:
    stem: str
    options: tuple[str, ...]
    answer_index: int  # ★ 只在后端 · 绝不下发前端
    explanation: str


def _load_exams() -> dict[str, tuple[ExamQuestion, ...]]:
    """从后端 JSON 加载 6 模块题库(import 时一次)· question→stem 映射。"""
    raw = json.loads(_QUESTIONS_FILE.read_text(encoding="utf-8"))
    return {
        stage: tuple(
            ExamQuestion(
                stem=q["question"],
                options=tuple(q["options"]),
                answer_index=int(q["answerIndex"]),
                explanation=q["explanation"],
            )
            for q in items
        )
        for stage, items in raw.items()
    }


# 6 模块结业测验题(★答案仅后端 · 从 exam_questions.json 加载)
EXAMS: dict[str, tuple[ExamQuestion, ...]] = _load_exams()


# ============================================================================
# 判分与取题(答案仅后端 · 前端不可见)
# ============================================================================


def has_exam(stage: str) -> bool:
    return stage in EXAMS


def exam_total(stage: str) -> int:
    return len(EXAMS.get(stage, ()))


def pass_line(total: int) -> int:
    """及格题数 = 总题数 × PASS_RATIO 向上取整(0 题 → 0)。"""
    return math.ceil(total * PASS_RATIO) if total > 0 else 0


@dataclass(frozen=True)
class PublicQuestion:
    """下发前端的题目 · ★只含 stem + options,绝无 answer_index/explanation(防作弊)。"""

    stem: str
    options: tuple[str, ...]


def public_questions(stage: str) -> list[PublicQuestion]:
    """前端用题目(去答案/去解析)。"""
    return [PublicQuestion(stem=q.stem, options=q.options) for q in EXAMS.get(stage, ())]


@dataclass(frozen=True)
class QuestionResult:
    question_index: int
    your_answer: int | None
    correct_answer: int
    is_correct: bool
    explanation: str


@dataclass(frozen=True)
class ExamScore:
    stage: str
    score: int
    total: int
    pass_line: int
    passed: bool
    results: list[QuestionResult]  # 提交后才回传(含正确答案+解析,供复盘)


def score_exam(stage: str, answers: list[int]) -> ExamScore:
    """★后端权威判分:用本表答案算 score/total/passed · 前端传的分数一律不信。

    answers[i] = 第 i 题选中的【原始】选项下标(前端洗牌后须映射回原序提交)。
    缺答(answers 不足)或越界下标按答错处理。
    """
    questions = EXAMS.get(stage, ())
    total = len(questions)
    results: list[QuestionResult] = []
    score = 0
    for i, q in enumerate(questions):
        your = answers[i] if i < len(answers) else None
        is_correct = your == q.answer_index
        if is_correct:
            score += 1
        results.append(
            QuestionResult(
                question_index=i,
                your_answer=your,
                correct_answer=q.answer_index,
                is_correct=is_correct,
                explanation=q.explanation,
            ),
        )
    line = pass_line(total)
    return ExamScore(
        stage=stage,
        score=score,
        total=total,
        pass_line=line,
        passed=total > 0 and score >= line,
        results=results,
    )
