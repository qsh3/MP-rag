"""
Pydantic 请求/响应模型
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# 知识库
# ═══════════════════════════════════════════════════════════

class CreateKBRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="知识库名称")
    description: str = Field("", max_length=500, description="描述")


class UpdateKBRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class KBResponse(BaseModel):
    id: str
    name: str
    description: str
    document_count: int = 0
    chunk_count: int = 0
    created_at: str
    ragflow_dataset_id: Optional[str] = None


class KBListResponse(BaseModel):
    total: int
    items: list[KBResponse]


# ═══════════════════════════════════════════════════════════
# 文档
# ═══════════════════════════════════════════════════════════

class DocResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size: int
    status: str  # "processing" | "ready" | "error"
    chunk_count: int = 0
    created_at: str
    kb_id: str
    tags: str = ""


class DocListResponse(BaseModel):
    total: int
    items: list[DocResponse]


class DocChunkResponse(BaseModel):
    id: str
    content: str
    metadata: dict = {}


# ═══════════════════════════════════════════════════════════
# 问答
# ═══════════════════════════════════════════════════════════

class AskRequest(BaseModel):
    kb_id: str = Field(..., description="知识库 ID")
    question: str = Field(..., min_length=1, max_length=2000, description="问题")
    top_k: int = Field(5, ge=1, le=20, description="检索数量")
    stream: bool = Field(True, description="是否流式返回")
    session_id: Optional[str] = Field(None, description="会话 ID，用于多轮对话")


class SourceDoc(BaseModel):
    doc_name: str
    doc_id: str
    chunk_text: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceDoc]
    kb_id: str
    question: str


class ChatHistoryItem(BaseModel):
    id: str
    kb_id: str
    session_id: str
    question: str
    answer: str
    sources: list[SourceDoc]
    created_at: str


# ═══════════════════════════════════════════════════════════
# 评估
# ═══════════════════════════════════════════════════════════

class EvalRunRequest(BaseModel):
    kb_id: str = Field(..., description="知识库 ID")
    test_questions: Optional[list[str]] = Field(None, description="指定测试问题（可选，不传则从历史采样）")
    max_samples: int = Field(10, ge=1, le=50, description="最大评估样本数（默认10）")


class EvalReviewRequest(BaseModel):
    kb_id: str = Field(..., description="知识库 ID")
    max_samples: int = Field(10, ge=1, le=50, description="最大复审样本数（默认10）")


class EvalMetric(BaseModel):
    name: str
    score: float
    description: str
    review_score: Optional[float] = None  # 复审者调整后的分数


class ReviewDetail(BaseModel):
    reviewed: bool = False
    review_status: str = "ok"  # "ok" | "degraded" | "not_reviewed"
    adjustments: list[str] = []  # ["faithfulness: 0.70->0.80 because..."]
    reason: str = ""
    reviewed_count: int = 0
    avg_review_scores: dict = {}


class EvalReportResponse(BaseModel):
    kb_id: str
    kb_name: str
    sample_count: int
    metrics: list[EvalMetric]
    new_evaluated: int = 0
    created_at: str
    review: Optional[ReviewDetail] = None


# ═══════════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status: str  # "healthy" | "degraded"
    ragflow: str  # "connected" | "unavailable"
    deepseek: str
    mysql: str
    qdrant: str = "configured"


# ═══════════════════════════════════════════════════════════
# 用户认证
# ═══════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)
    tags: str = Field("", max_length=500, description="权限标签，逗号分隔")


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: str
    username: str
    role: str
    tags: str = ""
    is_active: int = 1


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


# ═══════════════════════════════════════════════════════════
# 标签目录
# ═══════════════════════════════════════════════════════════

class TagResponse(BaseModel):
    id: str
    name: str


class TagCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="标签名称")


# ═══════════════════════════════════════════════════════════
# 管理员 — 用户管理
# ═══════════════════════════════════════════════════════════

class AdminUpdateUserRequest(BaseModel):
    tags: Optional[str] = Field(None, description="权限标签")
    role: Optional[str] = Field(None, description="角色: admin 或 user")
    is_active: Optional[int] = Field(None, description="0=禁用, 1=启用")


# ═══════════════════════════════════════════════════════════
# 文档更新
# ═══════════════════════════════════════════════════════════

class UpdateDocRequest(BaseModel):
    tags: Optional[str] = Field(None, description="权限标签")
