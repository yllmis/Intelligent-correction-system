/**
 * Flask API 封装
 *
 * 约定接口（后端实现参考）：
 *
 * GET  /api/health
 *      → { ok: true, version?: string }
 *
 * POST /api/upload          multipart: file
 *      → { success, image_id, image_url?, message? }
 *
 * POST /api/correct           JSON: { image_id }
 *      或 POST /api/correct   multipart: file（一步上传+批改）
 *      → CorrectResponse（见 types 注释）
 */
const ApiClient = (() => {
  const { API_BASE, REQUEST_TIMEOUT, MOCK_MODE } = AppConfig;

  class ApiError extends Error {
    constructor(message, code, status) {
      super(message);
      this.name = 'ApiError';
      this.code = code;
      this.status = status;
    }
  }

  /** 业务错误码，与需求文档异常处理对应 */
  const ErrorCode = {
    IMAGE_BLURRY: 'IMAGE_BLURRY',
    CUT_FAILED: 'CUT_FAILED',
    OCR_LOW_CONFIDENCE: 'OCR_LOW_CONFIDENCE',
    LLM_FAILED: 'LLM_FAILED',
    NETWORK: 'NETWORK',
    UNKNOWN: 'UNKNOWN',
  };

  const userMessages = {
    [ErrorCode.IMAGE_BLURRY]: '图像不清晰，请重新拍摄',
    [ErrorCode.CUT_FAILED]: '题目切分失败，请检查图像（或切题 API 是否正常）',
    [ErrorCode.OCR_LOW_CONFIDENCE]: '部分题目识别失败，需人工复核',
    [ErrorCode.LLM_FAILED]: '大模型批改失败，请稍后重试',
    [ErrorCode.NETWORK]: '网络异常，请检查后端服务是否启动',
    [ErrorCode.UNKNOWN]: '操作失败，请重试',
  };

  function getUserMessage(code, fallback) {
    return userMessages[code] || fallback || userMessages[ErrorCode.UNKNOWN];
  }

  async function fetchWithTimeout(url, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
    try {
      const res = await fetch(url, { ...options, signal: controller.signal });
      return res;
    } catch (err) {
      if (err.name === 'AbortError') {
        throw new ApiError('请求超时', ErrorCode.NETWORK, 0);
      }
      throw new ApiError('无法连接服务器', ErrorCode.NETWORK, 0);
    } finally {
      clearTimeout(timer);
    }
  }

  async function parseJson(res) {
    let data;
    try {
      data = await res.json();
    } catch {
      throw new ApiError('服务器返回格式错误', ErrorCode.UNKNOWN, res.status);
    }
    if (!res.ok) {
      const code = data.code || ErrorCode.UNKNOWN;
      const msg = data.message || getUserMessage(code);
      throw new ApiError(msg, code, res.status);
    }
    return data;
  }

  async function healthCheck() {
    if (MOCK_MODE) return { ok: true, mock: true };
    const res = await fetchWithTimeout(`${API_BASE}/api/health`, { method: 'GET' });
    return parseJson(res);
  }

  async function uploadImage(file) {
    if (MOCK_MODE) return mockUpload();
    const form = new FormData();
    form.append('file', file);
    const res = await fetchWithTimeout(`${API_BASE}/api/upload`, {
      method: 'POST',
      body: form,
    });
    const data = await parseJson(res);
    if (!data.success) {
      throw new ApiError(data.message || '上传失败', data.code || ErrorCode.UNKNOWN);
    }
    return data;
  }

  async function correctHomework(payload) {
    if (MOCK_MODE) return mockCorrect(payload);
    let res;
    if (payload instanceof FormData) {
      res = await fetchWithTimeout(`${API_BASE}/api/correct`, {
        method: 'POST',
        body: payload,
      });
    } else {
      res = await fetchWithTimeout(`${API_BASE}/api/correct`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    }
    const data = await parseJson(res);
    if (!data.success) {
      const code = data.code || ErrorCode.UNKNOWN;
      throw new ApiError(data.message || getUserMessage(code), code);
    }
    return data;
  }

  function mockUpload() {
    return Promise.resolve({
      success: true,
      image_id: 'mock-' + Date.now(),
      message: '模拟上传成功',
    });
  }

  function mockCorrect() {
    return new Promise((resolve) => {
      setTimeout(() => resolve(getMockCorrectResponse()), 1500);
    });
  }

  function getMockCorrectResponse() {
    return {
      success: true,
      question_count: 3,
      total_score: 22,
      max_score: 30,
      comment: '整体完成较好，计算题需注意进位。第 2 题解题思路正确但书写略潦草。',
      image_width: 800,
      image_height: 1100,
      questions: [
        {
          id: 1,
          order: 1,
          bbox: { x: 40, y: 80, width: 720, height: 180 },
          score: 10,
          max_score: 10,
          status: 'correct',
          ocr_text: '1. 计算：25 + 37 = ?',
          student_answer: '62',
          feedback: '回答正确',
        },
        {
          id: 2,
          order: 2,
          bbox: { x: 40, y: 300, width: 720, height: 200 },
          score: 8,
          max_score: 10,
          status: 'wrong',
          ocr_text: '2. 解方程：2x + 5 = 15',
          student_answer: 'x = 6',
          feedback: '应为 x = 5，请检查移项',
        },
        {
          id: 3,
          order: 3,
          bbox: { x: 40, y: 540, width: 720, height: 220 },
          score: 4,
          max_score: 10,
          status: 'need_review',
          ocr_text: '3. 简述光合作用的过程',
          student_answer: '（识别不清）',
          feedback: '识别失败，需人工复核',
        },
      ],
    };
  }

  /** 将后端相对路径转为可访问的完整 URL */
  function resolveImageUrl(url) {
    if (!url) return null;
    if (url.startsWith('data:') || url.startsWith('http://') || url.startsWith('https://')) {
      return url;
    }
    const base = API_BASE.replace(/\/$/, '');
    return url.startsWith('/') ? base + url : base + '/' + url;
  }

  return {
    ApiError,
    ErrorCode,
    getUserMessage,
    healthCheck,
    uploadImage,
    correctHomework,
    getMockCorrectResponse,
    resolveImageUrl,
  };
})();
