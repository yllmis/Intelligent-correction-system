"""大模型批改：调用 LLM API（通义千问 / DeepSeek）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GradingResult:
    """单道题批改结果。"""

    order: int
    score: int
    max_score: int
    status: str  # correct / wrong / partial
    feedback: str


MAX_RETRIES = 3


def grade(question_text: str, student_answer: str, order: int) -> GradingResult:
    """批改单道题。

    Args:
        question_text: 题干文本。
        student_answer: 学生答案。
        order: 题目序号。

    Returns:
        GradingResult。
    """
    # TODO: 构造 prompt → 调用 LLM API → 解析结果（含重试）
    raise NotImplementedError


def generate_comment(results: list[GradingResult]) -> str:
    """根据各题结果生成总体评语。"""
    # TODO: 汇总 prompt → 调用 LLM API
    raise NotImplementedError
