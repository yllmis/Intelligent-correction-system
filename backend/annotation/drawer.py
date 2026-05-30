"""批注绘制：在试卷图像上绘制分数和总分。"""

from __future__ import annotations

import base64

import cv2
import numpy as np


def compute_position(bbox: dict[str, int], image_width: int) -> tuple[int, int]:
    """计算批注绘制位置：题目右侧 +20px，上边缘 +10px。"""
    x = bbox["x"] + bbox["width"] + 20
    y = bbox["y"] + 10
    if x + 100 > image_width:
        x = max(bbox["x"] - 100, 10)
    return x, y


def draw_score(
    image: np.ndarray,
    bbox: dict[str, int],
    score: int,
    max_score: int,
    status: str,
) -> np.ndarray:
    """在图像上绘制单题分数批注。

    Returns:
        绘制后的图像副本。
    """
    # TODO: 中文文字绘制（需用 PIL）
    raise NotImplementedError


def image_to_base64(image: np.ndarray) -> str:
    """图像编码为 base64 PNG 字符串。"""
    _, buf = cv2.imencode(".png", image)
    return base64.b64encode(buf).decode("utf-8")
