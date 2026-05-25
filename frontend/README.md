# 智能作业批改 — 前端

基于需求文档实现的 Web 界面（HTML + CSS + 原生 JavaScript），通过 HTTP 对接 Flask 后端。

## 功能

- 本地上传 / 拖拽上传作业图片
- 摄像头拍摄（需 HTTPS 或 localhost）
- 上传、批改按钮与五步进度条
- 切题框 Canvas 叠加展示 + 题目数量
- 总分、总评、批注图、逐题详情
- 与需求文档一致的错误码提示

## 本地预览

### 方式一：仅前端演示（无需 Flask）

1. 打开 `js/config.js`，设置 `MOCK_MODE: true`
2. 用 VS Code Live Server 或直接打开 `index.html`
3. 上传任意图片 → 点击「开始批改」查看模拟结果

### 方式二：对接 Flask

1. `MOCK_MODE: false`，`API_BASE` 指向 Flask 地址
2. 后端实现 `/api/health`、`/api/upload`、`/api/correct`（见 `docs/API对接说明.md`）
3. 由 Flask 托管 `frontend` 静态目录，或配置 CORS

## 目录结构

```
frontend/
├── index.html
├── css/style.css
├── js/
│   ├── config.js    # API 地址、Mock 开关
│   ├── api.js       # 请求封装
│   ├── canvas.js    # 切题框绘制
│   └── app.js       # 主逻辑
└── docs/API对接说明.md
```
