"""统一响应格式与错误码定义。

前端约定的响应格式：
- 成功: {"success": true, ...数据字段}
- 失败: {"success": false, "code": "错误码", "message": "描述"}
"""

from __future__ import annotations

from typing import Any

from flask import jsonify


IMAGE_BLURRY = "IMAGE_BLURRY"           # 图像质量不达标
CUT_FAILED = "CUT_FAILED"              # 切题失败
OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"  # OCR 置信度过低
LLM_FAILED = "LLM_FAILED"             # 大模型调用失败
NETWORK = "NETWORK"                   # 网络错误
UNKNOWN = "UNKNOWN"                   # 未知错误


def success_response(data: dict[str, Any] | None = None, status: int = 200):
    """构造成功响应。

    Args:
        data: 需要合并到响应中的数据字段。
        status: HTTP 状态码，默认 200。

    Returns:
        Flask JSON 响应。
    """
    body = {"success": True}
    if data:
        body.update(data)
    return jsonify(body), status


def error_response(
    code: str = UNKNOWN,
    message: str = "",
    status: int = 400,
):
    """构造失败响应。

    Args:
        code: 错误码，取值见本模块常量。
        message: 可选的人类可读描述。
        status: HTTP 状态码，默认 400。

    Returns:
        Flask JSON 响应。
    """
    body: dict[str, Any] = {"success": False, "code": code}
    if message:
        body["message"] = message
    return jsonify(body), status
