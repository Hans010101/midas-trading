"""模块结业测验题库 + 判分 · 训练营 B 期刀2。

🔴 防作弊红线:正确答案(answer_index)【只在后端】· 前端只拿题干+选项(public_questions),
   提交选项下标后【后端用本表重新判分】(score_exam)· 前端传的分数一律不信。
🔴 纯增量:只读本题库 + 落 academy_exam_result · 不碰交易/支付/会员。

★ 初始为【示例题】(每模块 5 题 · 基于该模块已教内容),待 Hans 质检/扩充真题后替换。
   与随堂小测 quizzes.ts 独立(结业测验是另一套题)· 与 catalog STAGE_ORDER 同 6 模块 key。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# 达标线:答对 ≥ 80%(题数 × 0.8 向上取整 = 及格题数)
PASS_RATIO = 0.8


@dataclass(frozen=True)
class ExamQuestion:
    stem: str
    options: tuple[str, ...]
    answer_index: int  # ★ 只在后端 · 绝不下发前端
    explanation: str


# ============================================================================
# 6 模块结业测验题(★示例题待替换 · 答案仅后端)
# ============================================================================

EXAMS: dict[str, tuple[ExamQuestion, ...]] = {
    "basics": (
        ExamQuestion(
            "一根K线实体的上下边界由哪两个价格决定?",
            ("最高价和最低价", "开盘价和收盘价", "开盘价和最高价", "收盘价和最低价"),
            1,
            "实体由开盘价与收盘价围成;最高/最低价对应上下影线端点。",
        ),
        ExamQuestion(
            "“做空”指的是?",
            ("先买入等价格上涨", "先卖出等价格下跌再买回", "持有不动", "只在牛市操作"),
            1,
            "做空 = 先卖后买,赌价格下跌赚差价;与做多(先买后卖)方向相反。",
        ),
        ExamQuestion(
            "关于杠杆,下列说法正确的是?",
            ("只放大盈利不放大亏损", "同时放大盈利和亏损", "等于无风险借钱", "杠杆越高越安全"),
            1,
            "杠杆是双刃剑,等比例放大盈亏,杠杆越高爆仓风险越大。",
        ),
        ExamQuestion(
            "设置止损的主要目的是?",
            ("锁定最大亏损、保护本金", "保证一定盈利", "提高杠杆", "预测顶部"),
            0,
            "止损是离场纪律,看错时限制单笔亏损、保住本金活下去。",
        ),
        ExamQuestion(
            "支撑位通常指?",
            ("价格上方卖压区", "价格下方买盘较强、容易止跌的区域", "成交量最大点", "均线交叉点"),
            1,
            "支撑位是下方买盘强、易止跌的价位;阻力位则在上方。",
        ),
    ),
    "technical": (
        ExamQuestion(
            "均线(MA)的主要作用是?",
            ("预测精确价格", "平滑价格波动、看清趋势方向", "计算成交量", "替代K线"),
            1,
            "均线把杂乱波动抚平,帮助识别趋势方向与强弱。",
        ),
        ExamQuestion(
            "“金叉”一般指?",
            ("短期均线下穿长期均线", "短期均线上穿长期均线", "价格创新低", "成交量放大"),
            1,
            "金叉 = 短期均线上穿长期均线,常视为偏多信号;死叉相反。",
        ),
        ExamQuestion(
            "MACD 主要反映什么?",
            ("成交量", "价格动能与趋势变化", "市场情绪指数", "持仓量"),
            1,
            "MACD 由快慢均线之差构成,体现动能强弱与趋势转折。",
        ),
        ExamQuestion(
            "RSI 处于 70 以上通常被视为?",
            ("超卖", "超买", "无意义", "必然反转"),
            1,
            "RSI>70 常视为超买、>30 以下超卖,但极端行情可钝化,不等于必然反转。",
        ),
        ExamQuestion(
            "布林带收口(变窄)往往预示?",
            ("波动率降低、可能酝酿变盘", "立即上涨", "趋势结束", "成交量为零"),
            0,
            "布林带收窄代表波动率下降,常是变盘前的蓄势。",
        ),
    ),
    "chan": (
        ExamQuestion(
            "缠论中“顶分型”大致描述?",
            ("连续三根K线中间一根高点最高", "价格新低", "均线交叉", "成交量最大"),
            0,
            "顶分型由相邻三根K线构成,中间K线高点最高、低点也最高。",
        ),
        ExamQuestion(
            "缠论的“笔”由什么连接而成?",
            ("两个相邻且方向相反的分型", "两条均线", "两个中枢", "两根K线"),
            0,
            "一笔由相邻的顶分型与底分型连接,需满足独立K线根数等条件。",
        ),
        ExamQuestion(
            "“中枢”大致指?",
            ("至少三段走势的重叠区间", "最高价", "单根大阳线", "成交量堆积"),
            0,
            "中枢是连续若干段次级走势的重叠区间,代表多空暂时平衡的震荡区。",
        ),
        ExamQuestion(
            "缠论“第一类买点”通常出现在?",
            ("下跌趋势末端、背驰之后", "上涨中途", "中枢正中", "任意位置"),
            0,
            "一买多出现在下跌末段、出现背驰(动能衰竭)之后,博趋势反转。",
        ),
        ExamQuestion(
            "处理K线“包含关系”的目的是?",
            ("让分型/笔的判定更清晰", "增加交易次数", "计算杠杆", "预测点位"),
            0,
            "先按方向合并有包含关系的K线,才能干净地识别分型与笔。",
        ),
    ),
    "contract": (
        ExamQuestion(
            "永续合约没有?",
            ("交割日/到期日", "资金费率", "杠杆", "多空双向"),
            0,
            "永续合约无交割日,用资金费率机制把合约价格锚定现货。",
        ),
        ExamQuestion(
            "资金费率为正,通常表示?",
            ("空头付给多头", "多头付给空头、市场偏多", "交易所收税", "即将下跌"),
            1,
            "正费率时多头付给空头,反映多头拥挤;负费率则相反。",
        ),
        ExamQuestion(
            "“爆仓/强平”发生在?",
            ("保证金不足以维持仓位时", "盈利时", "挂单未成交时", "费率为零时"),
            0,
            "保证金低于维持保证金,仓位被强制平仓即爆仓,杠杆越高越易触发。",
        ),
        ExamQuestion(
            "持仓量(OI)上升一般意味着?",
            ("有新资金进场建仓", "一定上涨", "成交量为零", "费率必为负"),
            0,
            "OI 上升代表未平仓合约增加、新资金进场;需结合价格方向解读。",
        ),
        ExamQuestion(
            "降低爆仓风险的合理做法是?",
            ("满仓高杠杆", "控制杠杆、设止损、留足保证金", "不设止损扛单", "频繁加仓"),
            1,
            "控制杠杆、严格止损、保留保证金缓冲是降低强平风险的核心纪律。",
        ),
    ),
    "strategy": (
        ExamQuestion(
            "趋势跟踪策略的核心理念是?",
            ("追顶杀底", "顺势持有、截断亏损让利润奔跑", "高频套利", "逆势抄底"),
            1,
            "趋势跟踪顺势而为,亏损及时止损、盈利尽量持有。",
        ),
        ExamQuestion(
            "突破策略在什么时候进场?",
            ("价格有效突破关键区间/阻力", "价格在区间正中", "成交量为零", "费率为正"),
            0,
            "突破策略在价格有效突破关键位时跟进,需防假突破。",
        ),
        ExamQuestion(
            "均值回归策略假设?",
            ("价格永远单边", "价格偏离均值后倾向回归", "趋势永不结束", "杠杆越高越好"),
            1,
            "均值回归博取价格偏离后向均值回摆,适合震荡市、趋势market 易失效。",
        ),
        ExamQuestion(
            "关于马丁格尔(亏损加倍)策略,正确认识是?",
            ("稳赚不赔", "极端行情下有爆仓/巨亏风险", "无需止损", "杠杆无关"),
            1,
            "马丁格尔靠加倍摊平,遇单边极端行情可迅速放大亏损直至爆仓,风险极高。",
        ),
        ExamQuestion(
            "网格策略最适合的行情是?",
            ("单边急涨急跌", "区间震荡", "无成交", "停盘"),
            1,
            "网格在区间震荡中高抛低吸效果好;单边行情易被套或踏空。",
        ),
    ),
    "system": (
        ExamQuestion(
            "一份完整交易计划通常【不】包含?",
            ("进场条件", "止损止盈", "仓位管理", "保证一定盈利的承诺"),
            3,
            "交易计划含进场/出场/仓位/风险等,但没有任何策略能“保证盈利”。",
        ),
        ExamQuestion(
            "仓位管理的首要目标是?",
            ("一把梭哈", "控制单笔风险、避免被单次亏损击垮", "最大化杠杆", "追求频繁交易"),
            1,
            "仓位管理核心是控制单笔风险敞口,保证长期生存。",
        ),
        ExamQuestion(
            "“复盘”的主要价值在于?",
            ("回顾交易、总结对错、改进体系", "预测明天涨跌", "增加交易次数", "炫耀盈利"),
            0,
            "复盘通过回顾已结束的交易,沉淀经验、修正错误、迭代体系。",
        ),
        ExamQuestion(
            "面对连续亏损,成熟交易者应?",
            ("加大杠杆翻本", "按纪律执行、控制情绪、必要时降频", "删除止损", "随意改计划"),
            1,
            "连亏时更要守纪律、控情绪,避免报复性交易扩大亏损。",
        ),
        ExamQuestion(
            "交易纪律的意义是?",
            ("限制灵活性所以没用", "让交易可重复、抵御情绪干扰", "保证每单盈利", "替代策略"),
            1,
            "纪律让交易系统可重复执行、抵抗贪婪与恐惧,是长期稳定的基础。",
        ),
    ),
}


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
