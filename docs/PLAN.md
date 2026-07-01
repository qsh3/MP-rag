# 知识库智能问答系统 — 实施计划

## 背景

将 `MP/` 从 AI 简历优化器 **完全替换** 为知识库问答系统。

## 架构决策

**以 RAGFlow 为核心引擎**（本机 Docker 部署，按需启动），FastAPI 做薄封装层。

参考： [QAnything](https://github.com/netease-youdao/QAnything)（两阶段检索架构）、[RAGAS](https://github.com/explodinggradients/ragas)（评估框架）

---

## 一、系统架构

```
┌──────────────────────────────────────────────────┐
│         FRONTEND (Vue 3 + Ant Design Vue 4)       │
│  知识库管理 │ 文档上传 │ 问答对话 │ 评估报告         │
└────────────────────┬─────────────────────────────┘
                     │ HTTP/SSE
┌────────────────────▼─────────────────────────────┐
│            FASTAPI BACKEND (薄封装层)              │
│                                                    │
│  /api/v1/kb  │  /api/v1/docs  │  /api/v1/qa       │
│                      │                             │
│  ┌───────────────────▼──────────────────────────┐ │
│  │  kb_service   │  qa_service                  │ │
│  │  (MySQL CRUD) │  ①调RAGFlow检索              │ │
│  │               │  ②调DeepSeek生成              │ │
│  │               │  ③SSE流式返回                 │ │
│  └───────┬───────┴──────────────┬───────────────┘ │
└──────────┼──────────────────────┼─────────────────┘
           │                      │
    ┌──────▼──────┐  ┌────────────▼────────────┐
    │   MySQL     │  │       RAGFlow            │
    │  KB元数据    │  │  (Docker, 按需启动)       │
    │  聊天记录    │  │  ┌───────────────────┐  │
    │  评估数据    │  │  │ 文档解析+分块     │  │
    └─────────────┘  │  │ 向量存储+Embedding│  │
                     │  │ 混合检索+Reranker │  │
                     │  └───────────────────┘  │
                     └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │       DeepSeek API       │
                     │       (LLM 生成)          │
                     └─────────────────────────┘
```

### 两条核心流水线

**📥 文档入库：** 上传 → RAGFlow 解析+分块+Embedding → MySQL 记录元数据

```
POST /docs → 保存到 data/uploads/ → 上传到 RAGFlow dataset
→ RAGFlow 自动解析/分块/向量化 → 更新 MySQL 状态
```

**🔍 智能问答：**

```
提问 → RAGFlow 混合检索(向量+BM25+Reranker) → 构建 Prompt → DeepSeek SSE流式生成
```

### 职责划分

| 组件 | 负责 | 不负责 |
|------|------|--------|
| **RAGFlow** | 文档解析、分块、Embedding、向量存储、混合检索 | LLM 生成 |
| **FastAPI** | API 路由、文件上传、调用 RAGFlow + DeepSeek、SSE 推送 | 文档处理 |
| **DeepSeek** | LLM 生成（流式）、Reranker | — |
| **MySQL** | KB 元数据、文档记录、聊天历史、评估数据 | — |
| **ragas** | 评估 Faithfulness/Relevancy/Precision | — |

---

## 二、改造 rag_client.py

现有 client 已经封装了核心接口，需要扩展：

| 现有方法 | 改造 |
|------|------|
| `create_dataset()` | ✅ 直接复用 — 一个 dataset = 一个知识库 |
| `get_or_create_dataset()` | ✅ 直接复用 |
| `parse_resume()` | 🔧 重命名为 `upload_document()`，通用化 |
| `search_examples()` | ✅ 直接复用 — 即混合检索 |
| `seed_examples()` | 🔧 重命名为 `upload_batch()` |
| ❌ 新增 | `delete_document()` — 删除文档及 chunks |
| ❌ 新增 | `list_documents()` — 列出 dataset 下文档 |
| ❌ 新增 | `get_document_status()` — 查询解析状态 |
| ❌ 新增 | `chat_completion()` — RAGFlow 原生对话（可选） |

### 本地降级策略（RAGFlow 未启动时）

```
RAGFlow 不可用
  ├── 文档解析：PyMuPDF(PDF) / python-docx(DOCX) / DashScope OCR(图片)
  ├── 分块：core/chunker.py（父子双层分块）
  ├── Embedding：DashScope text-embedding-v2
  ├── 向量存储：Qdrant Cloud（已有配置）
  └── 检索：Qdrant ANN 搜索
```

> 即：RAGFlow 在线时零成本享用完整 RAG 能力；离线时自动降级到本地组件链，系统仍可工作。

---

## 三、多格式文档支持

| 格式 | RAGFlow 在线 | RAGFlow 离线降级 |
|------|:---:|------|
| PDF | ✅ RAGFlow 深度解析（版面/表格/OCR） | PyMuPDF 纯文本 |
| DOCX | ✅ RAGFlow 解析 | python-docx |
| TXT/MD | ✅ 直接上传 | 原生读取 |
| JPG/PNG | ✅ RAGFlow OCR | DashScope qwen-vl-plus OCR |
| Excel/PPT | ✅ RAGFlow 解析 | ❌ 不支持 |

---

## 四、后端 API

```
POST   /api/v1/kb                    创建知识库（对应 RAGFlow dataset）
GET    /api/v1/kb                    列出知识库
GET    /api/v1/kb/{id}               知识库详情（文档数/分块数）
DELETE /api/v1/kb/{id}               删除知识库 + RAGFlow dataset

POST   /api/v1/kb/{id}/docs          上传文档（multipart）
GET    /api/v1/kb/{id}/docs          文档列表 + 处理状态
DELETE /api/v1/kb/{id}/docs/{did}    删除文档 + RAGFlow chunks

POST   /api/v1/qa/ask                提问（SSE 流式，含来源引用）
GET    /api/v1/qa/history/{kb_id}    历史问答

POST   /api/v1/eval/run              运行 RAGAS 评估
GET    /api/v1/eval/report/{kb_id}   评估报告
GET    /api/v1/health                健康检查（含 RAGFlow 连通性）
```

---

## 五、前端设计

**技术栈：** Vue 3 + TypeScript + Vite + Ant Design Vue 4 + Pinia

| 页面 | 功能 |
|------|------|
| DashboardPage | 知识库卡片列表，统计信息，RAGFlow 状态指示 |
| KnowledgeBasePage | 文档列表 + 拖拽上传 + 处理状态(处理中/就绪/失败) + 删除 |
| QAPage | 对话界面，SSE 流式输出，来源引用展开，知识库切换 |
| EvalPage | RAGAS 评估报告，指标趋势图 |

---

## 六、文件变更

### 新建

```
MP/
├── app.py                          # FastAPI 入口
├── config.py                       # 统一配置加载
├── api/
│   ├── __init__.py
│   ├── kb.py                       # 知识库 CRUD
│   ├── document.py                 # 文档上传/列表/删除
│   ├── qa.py                       # 问答 SSE 流式
│   └── eval.py                     # RAGAS 评估
├── services/
│   ├── __init__.py
│   ├── kb_service.py               # KB 业务逻辑
│   ├── qa_service.py               # RAGFlow检索 + DeepSeek生成
│   └── llm_service.py              # DeepSeek 调用封装
├── models/
│   ├── __init__.py
│   ├── schemas.py                  # Pydantic 模型
│   └── db_models.py                # SQLAlchemy ORM
├── core/
│   ├── __init__.py
│   ├── parser.py                   # 本地降级解析器（RAGFlow 离线时用）
│   └── chunker.py                  # 本地降级分块器
├── evaluation/
│   ├── __init__.py
│   ├── collector.py                # 问答数据收集
│   └── runner.py                   # RAGAS 评估
├── frontend/                       # Vue 3 完整项目
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       ├── router/index.ts
│       ├── api/                    # axios + SSE
│       ├── pages/                  # 4个页面
│       ├── components/             # 通用组件
│       ├── composables/            # 组合式函数
│       ├── stores/                 # Pinia 状态
│       ├── types/                  # TS 类型
│       └── styles/                 # 全局样式
└── tests/
    ├── test_qa_pipeline.py
    └── test_evaluation.py
```

### 修改

| 文件 | 改动 |
|------|------|
| `rag_client.py` | 重命名通用化（`parse_resume`→`upload_document`，新增 `delete_document`/`list_documents`），保持双引擎降级模式 |
| `requirements.txt` | 添加 `python-docx`, `Pillow`, `sqlalchemy`, `pymysql`, `ragas`, `datasets`，移除 `fpdf2` |
| `.gitignore` | 添加 `frontend/node_modules/`, `data/uploads/` |
| `.env.example` | 更新为知识库系统所需配置 |

### 删除

| 文件 | 原因 |
|------|------|
| `main.py` | 替换为 uvicorn 入口 |
| `agent.py` | 简历优化逻辑全部删除 |
| `data/output/` | 旧简历输出 |
| `data/chroma_db/` | 不再用 ChromaDB |

---

## 七、RAGAS 评估集成

### 4 项核心指标

| 指标 | 衡量什么 | 需基准答案 |
|------|---------|:---:|
| Faithfulness | 答案断言是否可追溯到检索文档 | ❌ |
| Answer Relevancy | 答案是否切题 | ❌ |
| Context Precision | 检索到的片段是否相关 | ❌ |
| Context Recall | 是否遗漏关键信息 | ✅ |

> 前 3 项零人工成本，LLM-as-Judge 自动评估。

### 数据收集

每次问答后自动记录到 MySQL `evaluation_records` 表：
```python
{"question": "...", "answer": "...", "contexts": [...]}
```
定期运行 RAGAS 评估，生成指标报告。

---

## 八、实施顺序

### Phase 1：改造 RAGFlow 客户端
- 重构 `rag_client.py`：通用化方法名、新增缺失接口
- `config.py` 统一配置

### Phase 2：后端骨架
- `models/schemas.py` + `models/db_models.py`
- `app.py` FastAPI 入口 + CORS
- `api/kb.py` + `api/document.py`（CRUD）

### Phase 3：问答管道
- `services/llm_service.py`（DeepSeek 流式调用）
- `services/qa_service.py`（RAGFlow 检索 → 构建 Prompt → DeepSeek 生成）
- `api/qa.py`（SSE 端点）

### Phase 4：降级路径
- `core/parser.py`（本地文档解析）
- `core/chunker.py`（本地分块）
- 嵌入 + Qdrant 降级检索

### Phase 5：评估系统
- `evaluation/collector.py` + `evaluation/runner.py`
- `api/eval.py`

### Phase 6：前端
- Vue 3 + Vite 项目初始化
- 4 个页面 + SSE 对话组件

### Phase 7：集成验证
- 端到端测试 + RAGAS 指标验证

---

## 九、验证方式

```bash
# 1. 启动 RAGFlow（Docker）
docker start ragflow  # 或 docker-compose up -d

# 2. 启动后端
python main.py   # → http://localhost:8000

# 3. 健康检查
curl http://localhost:8000/api/v1/health
# → {"ragflow": "connected", "deepseek": "ok", "mysql": "ok"}

# 4. 创建知识库 + 上传文档
curl -X POST http://localhost:8000/api/v1/kb \
  -H "Content-Type: application/json" \
  -d '{"name": "技术文档库"}'

curl -X POST http://localhost:8000/api/v1/kb/{kb_id}/docs \
  -F "files=@manual.pdf" -F "files=@policy.docx"

# 5. 问答测试
curl -X POST http://localhost:8000/api/v1/qa/ask \
  -H "Content-Type: application/json" \
  -d '{"kb_id": "{kb_id}", "question": "考勤制度是什么？"}'

# 6. 评估
curl -X POST http://localhost:8000/api/v1/eval/run \
  -d '{"kb_id": "{kb_id}"}'

# 7. 前端
cd frontend && npm install && npm run dev
```
