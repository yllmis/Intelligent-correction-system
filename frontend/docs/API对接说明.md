# 前端与 Flask API 对接说明

前端目录：`frontend/`  
默认后端地址：`http://127.0.0.1:5000`（在 `js/config.js` 中修改 `API_BASE`）

## 1. Flask 静态资源示例

```python
from flask import Flask, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)  # 若前后端分离部署需开启

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/health")
def health():
    return {"ok": True, "version": "1.0"}
```

## 2. 接口约定

### GET `/api/health`

检测服务是否可用。

**响应 200：**

```json
{ "ok": true, "version": "1.0" }
```

---

### POST `/api/upload`

上传作业图片（`multipart/form-data`，字段名 `file`）。

**成功响应：**

```json
{
  "success": true,
  "image_id": "uuid-or-path-id",
  "image_url": "/uploads/xxx.jpg",
  "message": "上传成功"
}
```

**失败响应（HTTP 4xx）：**

```json
{
  "success": false,
  "code": "IMAGE_BLURRY",
  "message": "图像不清晰，请重新拍摄"
}
```

| code | 含义 |
|------|------|
| `IMAGE_BLURRY` | 图像质量不达标 |
| `UNKNOWN` | 其他错误 |

---

### POST `/api/correct`

执行完整批改流程（预处理 → 切题 → OCR → 大模型批改 → 批注）。

**方式 A — 已上传：**

```json
{ "image_id": "上一步返回的 image_id" }
```

**方式 B — 一步批改：**

`multipart/form-data`，字段 `file`（与上传相同）。

**成功响应：**

```json
{
  "success": true,
  "question_count": 3,
  "total_score": 22,
  "max_score": 30,
  "comment": "整体完成较好…",
  "image_url": "/results/original.jpg",
  "annotated_image_url": "/results/annotated.jpg",
  "annotated_image_base64": null,
  "image_width": 800,
  "image_height": 1100,
  "questions": [
    {
      "id": 1,
      "order": 1,
      "bbox": { "x": 40, "y": 80, "width": 720, "height": 180 },
      "points": [[40,80],[760,80],[760,260],[40,260]],
      "score": 10,
      "max_score": 10,
      "status": "correct",
      "ocr_text": "题干文本",
      "student_answer": "学生答案",
      "feedback": "批改反馈"
    }
  ]
}
```

**题目 `status` 枚举：**

| 值 | 说明 |
|----|------|
| `correct` | 正确 |
| `wrong` | 错误 |
| `partial` | 部分正确 |
| `ocr_failed` | OCR 失败 |
| `need_review` | 需人工复核 |

**失败 `code`：**

| code | 前端提示 |
|------|----------|
| `IMAGE_BLURRY` | 图像不清晰，请重新拍摄 |
| `CUT_FAILED` | 题目切分失败… |
| `OCR_LOW_CONFIDENCE` | 识别失败需复核（可部分成功返回） |
| `LLM_FAILED` | 大模型批改失败，请重试 |

## 3. 前端调试

在 `js/config.js` 中设置：

```javascript
MOCK_MODE: true
```

无需启动 Flask 即可查看完整 UI 与模拟批改结果。

## 4. 跨域

若前端用 Live Server 单独打开，Flask 需配置 CORS 或使用上述同一域名托管静态页。
