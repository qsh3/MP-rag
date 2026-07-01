"""
SQLAlchemy ORM 模型 — MySQL 元数据存储

表：
- knowledge_bases: 知识库元数据
- documents: 文档记录
- chat_history: 问答历史
- evaluation_records: RAGAS 评估数据
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Float, ForeignKey, create_engine, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from config import get_mysql_url

Base = declarative_base()


def gen_id() -> str:
    return uuid.uuid4().hex[:16]


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════════════════════
# 知识库
# ═══════════════════════════════════════════════════════════

class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(String(32), primary_key=True, default=gen_id)
    name = Column(String(200), nullable=False, index=True)
    description = Column(String(1000), default="")
    ragflow_dataset_id = Column(String(64), nullable=True)  # RAGFlow 对应的 dataset id
    chunk_size = Column(Integer, default=500)
    chunk_overlap = Column(Integer, default=50)
    document_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    created_at = Column(String(32), default=now_str)
    updated_at = Column(String(32), default=now_str)

    documents = relationship("Document", back_populates="kb", cascade="all, delete-orphan")


# ═══════════════════════════════════════════════════════════
# 文档
# ═══════════════════════════════════════════════════════════

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)
    file_size = Column(Integer, default=0)
    file_path = Column(String(1000), default="")  # 本地存储路径
    ragflow_doc_id = Column(String(64), nullable=True)  # RAGFlow 对应的 document id
    status = Column(String(20), default="processing")  # processing | ready | error
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(String(32), default=now_str)

    kb = relationship("KnowledgeBase", back_populates="documents")


# ═══════════════════════════════════════════════════════════
# 聊天历史
# ═══════════════════════════════════════════════════════════

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(32), nullable=False, index=True, default=gen_id)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources = Column(Text, default="[]")  # JSON 字符串: [{"doc_name": "...", "score": 0.9, ...}]
    created_at = Column(String(32), default=now_str)


# ═══════════════════════════════════════════════════════════
# 评估记录（用于 RAGAS）
# ═══════════════════════════════════════════════════════════

class EvaluationRecord(Base):
    __tablename__ = "evaluation_records"

    id = Column(String(32), primary_key=True, default=gen_id)
    kb_id = Column(String(32), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    contexts = Column(Text, default="[]")  # JSON 字符串: 检索到的文档片段列表
    ground_truth = Column(Text, nullable=True)  # 可选的人工标注基准答案
    faithfulness = Column(Float, nullable=True)
    answer_relevancy = Column(Float, nullable=True)
    context_precision = Column(Float, nullable=True)
    context_recall = Column(Float, nullable=True)
    # 复审相关字段（跨厂商复审：Kimi 复审 DashScope 的评分）
    reviewed = Column(Integer, default=0)  # 0=未复审, 1=已复审, -1=复审失败
    review_faithfulness = Column(Float, nullable=True)
    review_answer_relevancy = Column(Float, nullable=True)
    review_context_precision = Column(Float, nullable=True)
    review_reason = Column(Text, nullable=True)
    review_changes = Column(Text, nullable=True)  # JSON 数组
    eval_raw = Column(Text, nullable=True)  # JSON: 评估者完整推理
    review_raw = Column(Text, nullable=True)  # JSON: 复审者原始输出
    created_at = Column(String(32), default=now_str)


# ═══════════════════════════════════════════════════════════
# 数据库引擎
# ═══════════════════════════════════════════════════════════

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_mysql_url(), pool_pre_ping=True, pool_recycle=3600)
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def init_db():
    """创建数据库（如不存在）和所有表"""
    from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
    import pymysql

    # 先建库
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
    )
    conn.cursor().execute(
        f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    conn.close()

    # 再建表
    Base.metadata.create_all(bind=get_engine())

    # 兼容旧表：添加 session_id 列
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE chat_history ADD COLUMN session_id VARCHAR(32) NOT NULL DEFAULT ''"
            ))
            conn.commit()
    except Exception:
        pass  # 列已存在则忽略

    # 兼容旧表：添加 review 相关列
    try:
        engine = get_engine()
        with engine.connect() as conn:
            review_migrations = [
                ("reviewed", "INTEGER DEFAULT 0"),
                ("review_faithfulness", "FLOAT"),
                ("review_answer_relevancy", "FLOAT"),
                ("review_context_precision", "FLOAT"),
                ("review_reason", "TEXT"),
                ("review_changes", "TEXT"),
                ("eval_raw", "TEXT"),
                ("review_raw", "TEXT"),
            ]
            for col_name, col_type in review_migrations:
                try:
                    conn.execute(text(
                        f"ALTER TABLE evaluation_records ADD COLUMN {col_name} {col_type}"
                    ))
                    conn.commit()
                except Exception:
                    pass  # 列已存在则忽略
    except Exception:
        pass

    print("[MySQL] 数据库和表已初始化")
