"""Flask 路由定义。

提供以下接口：
- GET  /api/health    健康检查
- POST /api/upload    上传作业图像
- POST /api/correct   触发批改（支持一步上传+批改 或 两步仅批改）

调用链路（correct 接口）：
  上传图像 → enhance_to_white_bg_black_text → auto_correct_paper_perspective
  → recognize_edu_paper_cut → [逐题 OCR → 逐题 LLM 批改] → 批注绘制 → 返回结果
"""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2
import numpy as np
from flask import Blueprint, current_app, request, send_from_directory

from backend.api.responses import error_response, success_response

# ── 直接调用根目录已有方法 ─────────────────────────────────────────────
from paper_perspective_correction import auto_correct_paper_perspective
from document_enhance import enhance_to_white_bg_black_text
from aliyun_paper_cut import (
    draw_detected_regions,
    recognize_edu_paper_cut,
    _iter_content_regions,
    _to_point_list,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ── 健康检查 ────────────────────────────────────────────────────────────
@api_bp.route("/health", methods=["GET"])
def health():
    return success_response({"ok": True, "version": "0.1.0"})


# ── 图像上传 ────────────────────────────────────────────────────────────
@api_bp.route("/upload", methods=["POST"])
def upload():
    """接收上传图像，保存到 uploads/，返回 image_id。

    请求: multipart/form-data，字段 "file"。
    """
    file = request.files.get("file")
    if not file:
        return error_response("UNKNOWN", "未选择文件")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png"}:
        return error_response("UNKNOWN", f"不支持的文件格式: {ext}")

    image_id = f"{uuid.uuid4().hex}{ext}"
    upload_dir = Path(current_app.config.get("UPLOAD_DIR", "uploads"))
    upload_dir.mkdir(exist_ok=True)
    save_path = upload_dir / image_id
    file.save(str(save_path))

    return success_response({
        "image_id": image_id,
        "image_url": f"/api/uploads/{image_id}",
    })


# ── 批改接口 ────────────────────────────────────────────────────────────
@api_bp.route("/correct", methods=["POST"])
def correct():
    """触发批改完整流程。

    两种调用方式：
    1. multipart/form-data + file（一步：上传 + 批改）
    2. application/json + image_id（两步：批改已上传图像）
    """
    # ── 1. 获取图像文件路径 ────────────────────────────────────────────
    upload_dir = Path(current_app.config.get("UPLOAD_DIR", "uploads"))

    if request.content_type and "multipart" in request.content_type:
        file = request.files.get("file")
        if not file:
            return error_response("UNKNOWN", "未选择文件")
        ext = Path(file.filename).suffix.lower()
        image_id = f"{uuid.uuid4().hex}{ext}"
        save_path = upload_dir / image_id
        save_path.parent.mkdir(exist_ok=True)
        file.save(str(save_path))
    else:
        data = request.get_json(silent=True) or {}
        image_id = data.get("image_id", "")
        save_path = upload_dir / image_id
        if not save_path.is_file():
            return error_response("UNKNOWN", f"图像不存在: {image_id}")

    image_path = str(save_path)

    # ── 2. 读取图像 ──────────────────────────────────────────────────
    image = cv2.imread(image_path)
    if image is None:
        return error_response("IMAGE_BLURRY", "图像无法读取，请重新上传")
    h, w = image.shape[:2]

    # ── 3. 图像增强（根目录 document_enhance.py）────────────────────
    enhanced = enhance_to_white_bg_black_text(image)

    # ── 4. 透视矫正（根目录 paper_perspective_correction.py）────────
    try:
        corrected, _matrix, _points, _mask, _mode = auto_correct_paper_perspective(image)
    except Exception:
        corrected = image  # 矫正失败则使用原图

    # ── 5. 保存矫正后图像，供切题 API 使用 ──────────────────────────
    corrected_path = upload_dir / f"corrected_{image_id}"
    cv2.imwrite(str(corrected_path), corrected)

    # ── 6. 调用阿里云切题（根目录 aliyun_paper_cut.py）──────────────
    try:
        cut_result = recognize_edu_paper_cut(str(corrected_path))
    except Exception as e:
        msg = str(e)
        if "PaperCutEmptyImage" in msg or "No paper is found" in msg:
            return error_response("CUT_FAILED", "未识别到题目，请确认图片中包含作业内容")
        return error_response("CUT_FAILED", f"切题失败: {msg}")

    # ── 7. 解析切题结果，提取每道题坐标 ────────────────────────────
    questions_data = []
    for i, (label, polygon) in enumerate(_iter_content_regions(cut_result), start=1):
        if len(polygon) < 4:
            continue
        pts = np.array(polygon, dtype=np.int32)
        x, y, bw, bh = cv2.boundingRect(pts.reshape(-1, 1, 2))
        questions_data.append({
            "id": i,
            "order": i,
            "label": label,
            "polygon": polygon,
            "bbox": {"x": int(x), "y": int(y), "width": int(bw), "height": int(bh)},
        })

    if not questions_data:
        return error_response("CUT_FAILED", "未检测到题目区域")

    # ── 8. 逐题 OCR + LLM 批改（待实现）────────────────────────────
    questions_out = []
    total_score = 0
    max_total = 0

    for q in questions_data:
        # TODO: 裁切题目区域 → 调用 RecognizeEduQuestionOcr → 调用 LLM 批改
        # 暂时用占位数据
        score = 0
        q_max = 10
        total_score += score
        max_total += q_max
        questions_out.append({
            "id": q["id"],
            "order": q["order"],
            "bbox": q["bbox"],
            "score": score,
            "max_score": q_max,
            "status": "need_review",
            "ocr_text": "",
            "student_answer": "",
            "feedback": "批改功能待实现",
        })

    # ── 9. 批注绘制（待实现）───────────────────────────────────────
    # TODO: 在 corrected 图像上绘制分数批注
    annotated_base64 = ""

    # ── 10. 返回结果（符合前端 API 契约）───────────────────────────
    return success_response({
        "question_count": len(questions_out),
        "total_score": total_score,
        "max_score": max_total,
        "comment": "批改功能开发中",
        "image_width": w,
        "image_height": h,
        "annotated_image_base64": annotated_base64,
        "image_url": f"/api/uploads/corrected_{image_id}",
        "questions": questions_out,
    })


# ── 静态文件服务 ────────────────────────────────────────────────────────
@api_bp.route("/uploads/<path:filename>")
def serve_upload(filename: str):
    upload_dir = current_app.config.get("UPLOAD_DIR", "uploads")
    return send_from_directory(upload_dir, filename)
