"""
统一配置加载 — 从 .env 读取所有外部服务配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载项目 .env（优先级高于系统环境变量）
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

# ── DeepSeek LLM ──────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("DEEPSEEK_V4_PRO_MODEL", "") or os.getenv("DEEPSEEK_FREE_MODEL", "deepseek-chat")
EVAL_MODEL = os.getenv("DEEPSEEK_V4_MODEL", "deepseek-v4-flash")  # 评估用轻量模型，降低成本
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))

# ── DashScope (阿里云 — Embedding + 视觉模型) ─────────────
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
EMBED_MODEL_TYPE = os.getenv("EMBED_MODEL_TYPE", "dashscope")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "text-embedding-v2")
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "") or DASHSCOPE_API_KEY
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "") or DASHSCOPE_BASE_URL
QWEN_VL_MODEL = os.getenv("QWEN_FREE_MODEL", "qwen-vl-plus")

# ── RAGFlow（企业级文档引擎）───────────────────────────────
RAGFLOW_BASE_URL = os.getenv("RAGFLOW_BASE_URL", "")
RAGFLOW_API_KEY = os.getenv("RAGFLOW_API_KEY", "")
USE_RAGFLOW = os.getenv("USE_RAGFLOW", "").lower() in ("1", "true", "yes")

# ── Qdrant Cloud（向量数据库 — RAGFlow 离线降级用）────────
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "hello_agents_vectors")
QDRANT_VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "1536"))
QDRANT_DISTANCE = os.getenv("QDRANT_DISTANCE", "cosine")
QDRANT_TIMEOUT = int(os.getenv("QDRANT_TIMEOUT", "30"))

# ── MySQL（元数据 / 聊天记录 / 评估数据）───────────────────
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "langgraph_memory")

# ── Neo4j（知识图谱 — 可选）────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# ── 应用设置 ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
TOP_K_RETRIEVAL = int(os.getenv("TOP_K_RETRIEVAL", "5"))
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", "0.3"))


def get_mysql_url() -> str:
    """构建 MySQL 连接 URL"""
    return f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"


def is_ragflow_available() -> bool:
    """检查 RAGFlow 是否可用"""
    return USE_RAGFLOW and bool(RAGFLOW_BASE_URL and RAGFLOW_API_KEY)


def is_qdrant_available() -> bool:
    """检查 Qdrant 是否可用（降级路径）"""
    return bool(QDRANT_URL and QDRANT_API_KEY)
