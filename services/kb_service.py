"""
知识库业务逻辑 — MySQL CRUD + RAGFlow 同步
"""
import json
import os
from typing import Optional

from models.db_models import (
    get_session, KnowledgeBase, Document, ChatHistory,
    EvaluationRecord, Tag, now_str, gen_id,
)
from rag_client import get_client as get_rag_client


# ═══════════════════════════════════════════════════════════
# 标签权限工具
# ═══════════════════════════════════════════════════════════

def _parse_tags(tags_str: str) -> set[str]:
    """将逗号分隔的标签字符串转为集合"""
    if not tags_str or not tags_str.strip():
        return set()
    return {t.strip() for t in tags_str.split(",") if t.strip()}


def get_accessible_ragflow_doc_ids(user, kb_id: str) -> list[str] | None:
    """获取用户可访问的文档 ragflow_doc_id 列表（两级过滤第一步）

    权限规则：
    - admin → 不受限
    - 无标签用户 → 只能看无标签文档（纯公开）
    - 有标签用户 → 无标签文档 + 标签匹配的文档

    Returns:
        None  — 无限制（仅 admin）
        []    — 无任何可访问文档
        [...] — 允许的 ragflow_doc_id 列表
    """
    # admin 不受限
    if hasattr(user, "role") and user.role == "admin":
        return None

    user_tags = _parse_tags(getattr(user, "tags", ""))

    session = get_session()
    try:
        docs = session.query(Document).filter_by(kb_id=kb_id).all()
        allowed = []
        for doc in docs:
            doc_tags = _parse_tags(doc.tags or "")
            if not doc_tags:
                # 无标签文档 = 公开，所有人可见
                allowed.append(doc.ragflow_doc_id)
            elif user_tags and user_tags & doc_tags:
                # 用户标签与文档标签有交集
                allowed.append(doc.ragflow_doc_id)
        return allowed
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════
# 知识库管理
# ═══════════════════════════════════════════════════════════

def create_kb(name: str, description: str = "") -> dict:
    """创建知识库：MySQL 记录 + RAGFlow dataset"""
    rag = get_rag_client()
    session = get_session()

    try:
        # 创建 MySQL 记录
        kb = KnowledgeBase(name=name, description=description)
        session.add(kb)
        session.flush()

        # 创建 RAGFlow dataset（名称为 kb_{id} 避免重复）
        ragflow_name = "kb_%s" % kb.id
        dataset_id = rag.create_dataset(ragflow_name)

        if dataset_id:
            kb.ragflow_dataset_id = dataset_id
            session.commit()
        else:
            session.commit()

        return _kb_to_dict(kb)

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def list_kbs() -> list[dict]:
    """列出所有知识库"""
    session = get_session()
    try:
        kbs = session.query(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()).all()
        return [_kb_to_dict(kb) for kb in kbs]
    finally:
        session.close()


def get_kb(kb_id: str) -> Optional[dict]:
    """获取单个知识库详情"""
    session = get_session()
    try:
        kb = session.query(KnowledgeBase).filter_by(id=kb_id).first()
        return _kb_to_dict(kb) if kb else None
    finally:
        session.close()


def update_kb(kb_id: str, name: str = None, description: str = None) -> Optional[dict]:
    """更新知识库"""
    session = get_session()
    try:
        kb = session.query(KnowledgeBase).filter_by(id=kb_id).first()
        if not kb:
            return None
        if name is not None:
            kb.name = name
        if description is not None:
            kb.description = description
        kb.updated_at = now_str()
        session.commit()
        return _kb_to_dict(kb)
    finally:
        session.close()


def delete_kb(kb_id: str) -> bool:
    """删除知识库：MySQL 记录 + RAGFlow dataset"""
    rag = get_rag_client()
    session = get_session()
    try:
        kb = session.query(KnowledgeBase).filter_by(id=kb_id).first()
        if not kb:
            return False

        # 删除 RAGFlow dataset
        if kb.ragflow_dataset_id:
            rag.delete_dataset(kb.ragflow_dataset_id)

        # 删除本地文件
        upload_dir = os.path.join("data", "uploads", kb_id)
        if os.path.exists(upload_dir):
            import shutil
            shutil.rmtree(upload_dir)

        session.delete(kb)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════
# 文档管理
# ═══════════════════════════════════════════════════════════

def add_document(kb_id: str, filename: str, file_type: str,
                 file_size: int, file_path: str, tags: str = "") -> dict:
    """添加文档记录"""
    session = get_session()
    try:
        doc = Document(
            kb_id=kb_id, filename=filename, file_type=file_type,
            file_size=file_size, file_path=file_path, status="processing",
            tags=tags,
        )
        session.add(doc)

        # 更新知识库文档计数
        kb = session.query(KnowledgeBase).filter_by(id=kb_id).first()
        if kb:
            kb.document_count = (kb.document_count or 0) + 1

        session.commit()
        return _doc_to_dict(doc)
    finally:
        session.close()


def update_document_status(doc_id: str, status: str, ragflow_doc_id: str = None,
                           chunk_count: int = 0, error_message: str = None) -> dict:
    """更新文档状态"""
    session = get_session()
    try:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return {}
        doc.status = status
        if ragflow_doc_id:
            doc.ragflow_doc_id = ragflow_doc_id
        if chunk_count:
            doc.chunk_count = chunk_count

            # 同步更新 KB 的 chunk 计数
            kb = session.query(KnowledgeBase).filter_by(id=doc.kb_id).first()
            if kb:
                kb.chunk_count = (kb.chunk_count or 0) + chunk_count

        if error_message:
            doc.error_message = error_message
        session.commit()
        return _doc_to_dict(doc)
    finally:
        session.close()


def sync_documents_with_ragflow(kb_id: str):
    """同步 MySQL 文档记录与 RAGFlow 实际状态
    - RAGFlow 已删的 → MySQL 也删掉
    - RAGFlow 状态更新的 → MySQL 更新
    - RAGFlow 新增的（直接上传的）→ MySQL 补录
    """
    rag = get_rag_client()
    if not rag.ensure_available():
        return

    session = get_session()
    try:
        kb = session.query(KnowledgeBase).filter_by(id=kb_id).first()
        if not kb or not kb.ragflow_dataset_id:
            return

        # 获取 RAGFlow 实际文档列表
        rag_docs = rag.list_documents(kb.ragflow_dataset_id)
        rag_doc_map = {d["id"]: d for d in rag_docs}  # ragflow_doc_id → doc

        # 获取 MySQL 中的文档
        mysql_docs = session.query(Document).filter_by(kb_id=kb_id).all()

        # 整理 MySQL 中那些关联了 RAGFlow 的文档
        mysql_by_rag_id = {d.ragflow_doc_id: d for d in mysql_docs if d.ragflow_doc_id}

        removed_count = 0
        updated_count = 0

        for doc in mysql_docs:
            if doc.ragflow_doc_id and doc.ragflow_doc_id not in rag_doc_map:
                # RAGFlow 里已删除 → MySQL 也删
                if doc.file_path and os.path.exists(doc.file_path):
                    os.remove(doc.file_path)
                session.delete(doc)
                removed_count += 1
            elif doc.ragflow_doc_id and doc.ragflow_doc_id in rag_doc_map:
                # 更新状态
                rag_doc = rag_doc_map[doc.ragflow_doc_id]
                old_status = doc.status
                doc.status = rag_doc.get("status", doc.status)
                doc.chunk_count = rag_doc.get("chunk_count", doc.chunk_count)
                if old_status != doc.status:
                    updated_count += 1
            elif not doc.ragflow_doc_id:
                # 没有 RAGFlow ID 的孤立文档 → 删除
                if doc.file_path and os.path.exists(doc.file_path):
                    os.remove(doc.file_path)
                session.delete(doc)
                removed_count += 1

        # RAGFlow 中有但 MySQL 没有的文档（直接通过 RAGFlow 上传的）→ 补录
        existing_rag_ids = set(mysql_by_rag_id.keys())
        for rag_id, rag_doc in rag_doc_map.items():
            if rag_id not in existing_rag_ids:
                new_doc = Document(
                    kb_id=kb_id,
                    filename=rag_doc.get("name", "unknown"),
                    file_type="unknown",
                    file_size=rag_doc.get("size", 0),
                    file_path="",
                    status=rag_doc.get("status", "processing"),
                    chunk_count=rag_doc.get("chunk_count", 0),
                    ragflow_doc_id=rag_id,
                )
                session.add(new_doc)

        # 更新 KB 计数
        remaining = session.query(Document).filter_by(kb_id=kb_id).all()
        kb.document_count = len(remaining)
        kb.chunk_count = sum(d.chunk_count or 0 for d in remaining)

        session.commit()

        if removed_count or updated_count:
            print("[Sync] KB %s: 删除 %d 条, 更新 %d 条" % (kb_id, removed_count, updated_count))

    except Exception as e:
        session.rollback()
        print("[Sync] 同步失败: %s" % e)
    finally:
        session.close()


def list_documents(kb_id: str, user=None) -> list[dict]:
    """列出知识库下的文档（自动同步 RAGFlow 状态，按用户标签过滤）"""
    sync_documents_with_ragflow(kb_id)

    session = get_session()
    try:
        docs = session.query(Document).filter_by(kb_id=kb_id)\
            .order_by(Document.created_at.desc()).all()
        result = [_doc_to_dict(d) for d in docs]

        # 按用户标签过滤：无标签用户只能看无标签文档，有标签用户额外看匹配文档
        if user and getattr(user, "role", "") != "admin":
            user_tags = _parse_tags(getattr(user, "tags", ""))
            result = [
                d for d in result
                if not _parse_tags(d.get("tags", ""))
                or (user_tags and user_tags & _parse_tags(d.get("tags", "")))
            ]
        return result
    finally:
        session.close()


def get_document(doc_id: str) -> Optional[dict]:
    """获取单个文档详情"""
    session = get_session()
    try:
        doc = session.query(Document).filter_by(id=doc_id).first()
        return _doc_to_dict(doc) if doc else None
    finally:
        session.close()


def delete_document(doc_id: str) -> bool:
    """删除文档：MySQL 记录 + RAGFlow chunks + 本地文件"""
    rag = get_rag_client()
    session = get_session()
    try:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return False

        # 删除 RAGFlow 中的 chunks
        kb = session.query(KnowledgeBase).filter_by(id=doc.kb_id).first()
        if kb and kb.ragflow_dataset_id and doc.ragflow_doc_id:
            rag.delete_document(kb.ragflow_dataset_id, doc.ragflow_doc_id)

        # 删除本地文件
        if doc.file_path and os.path.exists(doc.file_path):
            os.remove(doc.file_path)

        # 更新 KB 计数
        if kb:
            kb.document_count = max(0, (kb.document_count or 1) - 1)
            kb.chunk_count = max(0, (kb.chunk_count or 0) - (doc.chunk_count or 0))

        session.delete(doc)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════
# 聊天历史
# ═══════════════════════════════════════════════════════════

def save_chat(kb_id: str, question: str, answer: str, sources: list,
              session_id: str = None, user_id: str = "") -> dict:
    """保存问答记录"""
    session = get_session()
    try:
        sid = session_id or gen_id()
        chat = ChatHistory(
            kb_id=kb_id, question=question, answer=answer,
            sources=json.dumps(sources, ensure_ascii=False),
            session_id=sid, user_id=user_id,
        )
        session.add(chat)
        session.commit()
        return {"id": chat.id, "session_id": sid, "created_at": chat.created_at}
    finally:
        session.close()


def get_chat_history(kb_id: str, limit: int = 50, user=None) -> list[dict]:
    """获取知识库的问答历史（按用户隔离：普通用户只看自己的，admin 看所有）"""
    session = get_session()
    try:
        q = session.query(ChatHistory).filter_by(kb_id=kb_id)
        if user and getattr(user, "role", "") != "admin":
            q = q.filter_by(user_id=user.id)
        chats = q.order_by(ChatHistory.created_at.desc()).limit(limit).all()
        return [{"id": c.id, "session_id": c.session_id or "",
                 "question": c.question, "answer": c.answer,
                 "sources": _parse_json(c.sources), "created_at": c.created_at} for c in chats]
    finally:
        session.close()


def get_session_history(kb_id: str, session_id: str, user=None) -> list[dict]:
    """获取指定会话的完整对话历史（按用户隔离）"""
    session = get_session()
    try:
        q = session.query(ChatHistory).filter_by(kb_id=kb_id, session_id=session_id)
        if user and getattr(user, "role", "") != "admin":
            q = q.filter_by(user_id=user.id)
        chats = q.order_by(ChatHistory.created_at.asc()).all()
        return [{"id": c.id, "question": c.question, "answer": c.answer,
                 "sources": _parse_json(c.sources), "created_at": c.created_at} for c in chats]
    finally:
        session.close()


def delete_session_history(kb_id: str, session_id: str, user=None) -> int:
    """删除指定会话的所有聊天记录（只能删自己的）"""
    session = get_session()
    try:
        q = session.query(ChatHistory).filter_by(kb_id=kb_id, session_id=session_id)
        if user and getattr(user, "role", "") != "admin":
            q = q.filter_by(user_id=user.id)
        count = q.delete()
        session.commit()
        return count
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════
# 评估记录
# ═══════════════════════════════════════════════════════════

def save_evaluation_record(kb_id: str, question: str, answer: str,
                           contexts: list, ground_truth: str = None,
                           user_id: str = "") -> str:
    """保存评估记录"""
    session = get_session()
    try:
        record = EvaluationRecord(
            kb_id=kb_id, question=question, answer=answer,
            contexts=json.dumps(contexts, ensure_ascii=False),
            ground_truth=ground_truth, user_id=user_id,
        )
        session.add(record)
        session.commit()
        return record.id
    finally:
        session.close()


def get_unevaluated_records(kb_id: str) -> list[dict]:
    """获取未评估的记录"""
    session = get_session()
    try:
        records = session.query(EvaluationRecord)\
            .filter_by(kb_id=kb_id)\
            .filter(EvaluationRecord.faithfulness.is_(None))\
            .all()
        return [_eval_to_dict(r) for r in records]
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════
# 标签目录管理
# ═══════════════════════════════════════════════════════════

def list_tags() -> list[dict]:
    """列出所有标签"""
    session = get_session()
    try:
        tags = session.query(Tag).order_by(Tag.created_at.asc()).all()
        return [{"id": t.id, "name": t.name} for t in tags]
    finally:
        session.close()


def create_tag(name: str) -> dict:
    """新建标签"""
    session = get_session()
    try:
        existing = session.query(Tag).filter_by(name=name).first()
        if existing:
            raise ValueError(f"标签 '{name}' 已存在")
        tag = Tag(name=name)
        session.add(tag)
        session.commit()
        return {"id": tag.id, "name": tag.name}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_tag(tag_id: str) -> bool:
    """删除标签"""
    session = get_session()
    try:
        tag = session.query(Tag).filter_by(id=tag_id).first()
        if not tag:
            return False
        session.delete(tag)
        session.commit()
        return True
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════
# 文档标签管理（admin）
# ═══════════════════════════════════════════════════════════

def update_document_tags(doc_id: str, tags: str) -> Optional[dict]:
    """更新文档标签（admin 专用）"""
    session = get_session()
    try:
        doc = session.query(Document).filter_by(id=doc_id).first()
        if not doc:
            return None
        doc.tags = tags
        session.commit()
        return _doc_to_dict(doc)
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════
# 帮助函数
# ═══════════════════════════════════════════════════════════

def _kb_to_dict(kb: KnowledgeBase) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description or "",
        "document_count": kb.document_count or 0,
        "chunk_count": kb.chunk_count or 0,
        "created_at": kb.created_at or "",
        "ragflow_dataset_id": kb.ragflow_dataset_id,
    }


def _doc_to_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "file_size": doc.file_size or 0,
        "status": doc.status,
        "chunk_count": doc.chunk_count or 0,
        "created_at": doc.created_at or "",
        "kb_id": doc.kb_id,
        "tags": doc.tags or "",
    }


def _parse_json(val) -> list:
    """安全解析 JSON 字符串"""
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _eval_to_dict(record: EvaluationRecord) -> dict:
    return {
        "id": record.id,
        "kb_id": record.kb_id,
        "question": record.question,
        "answer": record.answer,
        "contexts": _parse_json(record.contexts),
        "ground_truth": record.ground_truth,
        "created_at": record.created_at or "",
    }
