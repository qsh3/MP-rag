"""
企业知识库智能问答系统 — FastAPI 入口
"""
import sys
import io

# Windows 中文编码修复
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import PROJECT_ROOT
from api.kb import router as kb_router
from api.document import router as doc_router
from api.qa import router as qa_router
from api.eval import router as eval_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时
    print("=" * 50)
    print("  企业知识库智能问答系统 启动中...")
    print("=" * 50)

    from rag_client import get_client
    rag = get_client()
    print("  RAGFlow: %s" % ("已连接" if rag.available else "不可用（使用降级模式）"))

    # 初始化 MySQL 表
    try:
        from models.db_models import init_db
        init_db()
    except Exception as e:
        print("  [WARN] MySQL 初始化失败: %s（系统可运行但无持久化）" % e)

    print("  API 文档: http://localhost:8000/docs")
    yield
    print("\n系统关闭。")


app = FastAPI(
    title="企业知识库智能问答系统",
    description="基于 RAGFlow + DeepSeek 的企业级 RAG 知识库问答平台",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(kb_router)
app.include_router(doc_router)
app.include_router(qa_router)
app.include_router(eval_router)


@app.get("/api/v1/health")
def health_check():
    """健康检查"""
    from rag_client import get_client
    rag = get_client()

    # DeepSeek 检查
    try:
        from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
        deepseek_ok = bool(DEEPSEEK_API_KEY)
    except Exception:
        deepseek_ok = False

    return {
        "status": "healthy",
        "ragflow": "connected" if rag.ping() else "unavailable",
        "deepseek": "ok" if deepseek_ok else "unconfigured",
        "mysql": "configured",
        "qdrant": "configured",
    }
