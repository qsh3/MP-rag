# MP-RAG — 企业知识库智能问答系统

基于 **RAG（检索增强生成）** 架构的企业级知识库问答平台。支持多格式文档自动解析、混合检索与 LLM 流式生成，内置 RAGAS 自动评估体系。

> 🎓 独立全栈项目 | Python FastAPI + Vue 3 + RAGFlow + DeepSeek + MySQL

---

## ✨ 核心特性

- 📄 **多格式文档解析** — PDF、Word、Excel、PPT、TXT、图片（OCR），由 RAGFlow 引擎自动分块与向量化
- 🔍 **混合检索** — 向量检索 + BM25 关键词检索 + Reranker 重排序，提升召回质量
- 💬 **智能问答** — 短查询关键词提取 → 混合检索 → DeepSeek SSE 流式生成，支持多轮对话
- 📊 **RAGAS 质量评估** — LLM-as-Judge 自动评估：忠实度、答案相关性、上下文精确度（位置加权），对齐 Ragas 官方实现
- ⚡ **增量评估** — 跳过已有评分的条目，ThreadPoolExecutor 并发调用，deepseek-v4-flash 降本
- 🎨 **前后端分离** — FastAPI RESTful API + Vue 3 + Ant Design Vue 4 专业 UI

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────┐
│         前端 (Vue 3 + TypeScript + Ant Design)    │
│  知识库管理 │ 文档上传 │ 流式问答 │ 评估报告      │
└────────────────────┬────────────────────────────┘
                     │ HTTP / SSE
┌────────────────────▼────────────────────────────┐
│              FastAPI 后端 (Python)                │
│                                                    │
│  /api/v1/kb  │  /api/v1/docs  │  /api/v1/qa       │
│  /api/v1/eval                                  │
│                      │                             │
│  ┌───────────────────▼──────────────────────────┐ │
│  │  kb_service  │  qa_service  │  llm_service   │ │
│  └───────┬───────┴──────────────┬───────────────┘ │
└──────────┼──────────────────────┼─────────────────┘
           │                      │
    ┌──────▼──────┐  ┌────────────▼────────────┐
    │   MySQL     │  │       RAGFlow            │
    │  元数据      │  │  文档解析 + 分块 + 向量化  │
    │  聊天记录    │  │  混合检索 + Reranker      │
    │  评估数据    │  │  (Docker 本地部署)         │
    └─────────────┘  └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │       DeepSeek API       │
                     │   deepseek-v4-pro (生成)  │
                     │   deepseek-v4-flash (评估)│
                     └─────────────────────────┘
```

### 两条核心流水线

**📥 文档入库：** 上传 → RAGFlow 解析 + 分块 + Embedding → MySQL 记录元数据

**🔍 智能问答：** 关键词提取 → RAGFlow 混合检索（向量 + BM25 + Reranker）→ DeepSeek SSE 流式生成

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | Python FastAPI + Uvicorn |
| **前端** | Vue 3 + TypeScript + Vite |
| **UI 库** | Ant Design Vue 4 |
| **文档引擎** | RAGFlow（Docker 部署） |
| **LLM** | DeepSeek（deepseek-v4-pro / v4-flash） |
| **数据库** | MySQL（SQLAlchemy ORM） |
| **向量存储** | Infinity（RAGFlow 内置）/ Qdrant Cloud（降级） |
| **评估框架** | RAGAS（LLM-as-Judge） |
| **Embedding** | DashScope text-embedding-v2 |

---

## 🚀 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- Docker（运行 RAGFlow）
- DeepSeek API Key

### 1. 克隆项目

```bash
git clone https://github.com/qsh3/MP-rag.git
cd MP-rag
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key：
#   DEEPSEEK_API_KEY=sk-xxx
#   MYSQL_PASSWORD=xxx
```

### 3. 安装后端依赖

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. 初始化数据库

```bash
python init_db.py
```

### 5. 启动 RAGFlow（可选但推荐）

```bash
# 参考 RAGFlow 官方文档启动 Docker 服务
# 启动后在 .env 中配置：
#   USE_RAGFLOW=true
#   RAGFLOW_BASE_URL=http://localhost
#   RAGFLOW_API_KEY=ragflow-xxx
```

### 6. 构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

### 7. 启动后端

```bash
python main.py
# 访问 http://localhost:8000
# API 文档: http://localhost:8000/docs
```

---

## 📡 API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/kb` | 创建知识库 |
| `GET` | `/api/v1/kb` | 列出知识库 |
| `GET` | `/api/v1/kb/{id}` | 知识库详情 |
| `DELETE` | `/api/v1/kb/{id}` | 删除知识库 |
| `POST` | `/api/v1/kb/{id}/docs` | 上传文档 |
| `GET` | `/api/v1/kb/{id}/docs` | 文档列表 |
| `DELETE` | `/api/v1/kb/{id}/docs/{did}` | 删除文档 |
| `POST` | `/api/v1/qa/ask` | 提问（SSE 流式） |
| `GET` | `/api/v1/qa/history/{kb_id}` | 历史问答 |
| `POST` | `/api/v1/eval/run` | 运行 RAGAS 评估 |
| `GET` | `/api/v1/eval/report/{kb_id}` | 评估报告 |
| `GET` | `/api/v1/health` | 健康检查 |

---

## 📊 RAGAS 评估指标

| 指标 | 说明 | 计算方式 |
|------|------|---------|
| **Faithfulness** 忠实度 | 答案中的断言是否能从检索文档中找到依据 | 拆解陈述 → 逐条验证 → 有依据数/总数 |
| **Answer Relevancy** 答案相关性 | 答案是否直接、完整地回答了用户问题 | 分解问题要点 → 逐条检查覆盖 → 覆盖数/总数 |
| **Context Precision** 上下文精确度 | 检索文档的排名质量 | 位置加权 Precision@k（Ragas 官方公式） |

> 三项指标均为 0-1 分数，无需人工标注基准答案。

---

## 📁 项目结构

```
MP/
├── main.py                  # 应用入口（含缓存自动清理）
├── app.py                   # FastAPI 应用定义
├── config.py                # 统一配置（从 .env 加载）
├── requirements.txt         # Python 依赖
├── rag_client.py            # RAGFlow API 封装
│
├── api/                     # API 路由层
│   ├── kb.py                # 知识库 CRUD
│   ├── document.py          # 文档上传/列表/删除
│   ├── qa.py                # 问答 SSE 流式
│   └── eval.py              # 评估运行/报告
│
├── services/                # 业务逻辑层
│   ├── kb_service.py        # 知识库业务
│   ├── qa_service.py        # RAG 问答管道（含关键词提取）
│   └── llm_service.py       # DeepSeek 调用封装（流式 + JSON）
│
├── models/                  # 数据模型
│   ├── schemas.py           # Pydantic 请求/响应模型
│   └── db_models.py         # SQLAlchemy ORM 模型
│
├── evaluation/              # RAGAS 评估系统
│   ├── collector.py         # 问答数据收集（去重）
│   └── runner.py            # 评估运行器（并发 + 增量）
│
├── core/                    # 核心模块
│   ├── chunker.py           # 本地降级分块器
│   └── parser.py            # 本地降级文档解析器
│
└── frontend/                # Vue 3 前端
    └── src/
        ├── pages/           # Dashboard / KB / QA / Eval 页面
        ├── api/             # axios + SSE 客户端
        ├── stores/          # Pinia 状态管理
        └── types/           # TypeScript 类型定义
```

---

## 🔧 设计决策

| 决策 | 理由 |
|------|------|
| **RAGFlow 为核心引擎** | 开箱即用的文档解析 + 混合检索 + Reranker，避免重复造轮子 |
| **DeepSeek 而非 OpenAI** | 中文能力强、成本低、API 兼容 OpenAI SDK |
| **SSE 而非 WebSocket** | 单向流式生成场景，SSE 实现更简单、代理兼容更好 |
| **评估用 flash 模型** | deepseek-v4-flash 成本远低于 pro，评估场景只需结构化判断 |
| **增量评估** | 避免对已评分条目重复调用 LLM，节省 token |
| **位置加权 Context Precision** | 对齐 Ragas 官方公式，排在前的相关片段得分更高 |

---

## 📝 License

MIT License
