"""
文本分块器 — 父子双层分块（参考 QAnything 设计）

- Child Chunk: 500-1000 字符，用于向量检索（精准匹配）
- Parent Chunk: 2000-4000 字符，喂给 LLM 生成答案（完整上下文）

检索流程：Child 匹配 → 找到所属 Parent → 将 Parent 及其周围 Children 送入 LLM
"""
import re
from typing import Optional
from config import CHUNK_SIZE, CHUNK_OVERLAP

# 中文友好的分割符优先级
_SEPARATORS = ["\n\n", "\n", "。", ".", "；", ";", "，", ",", " ", ""]

# 大小参数
CHILD_SIZE = CHUNK_SIZE  # 默认 500
CHILD_OVERLAP = CHUNK_OVERLAP  # 默认 50
PARENT_SIZE = CHILD_SIZE * 4  # 默认 2000
PARENT_OVERLAP = CHILD_OVERLAP * 2  # 默认 100


def _find_best_separator(text: str) -> str:
    """找到文本中最合适的分割符"""
    for sep in _SEPARATORS:
        if sep in text:
            return sep
    return ""


def _split_by_size(text: str, chunk_size: int, overlap: int) -> list[str]:
    """按大小递归分割文本"""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    sep = _find_best_separator(text)
    if not sep:
        # 强制按字符切分
        chunks = []
        for i in range(0, len(text), chunk_size - overlap):
            chunks.append(text[i:i + chunk_size])
        return chunks

    parts = text.split(sep)
    chunks = []
    current = ""

    for part in parts:
        if len(current) + len(sep) + len(part) <= chunk_size:
            current = (current + sep + part) if current else part
        else:
            if current.strip():
                chunks.append(current)
            current = part

    if current.strip():
        chunks.append(current)

    return chunks


def chunk_text(text: str,
               child_size: int = None,
               child_overlap: int = None,
               parent_size: int = None,
               parent_overlap: int = None) -> list[dict]:
    """父子双层分块

    Args:
        text: 待分块的原始文本

    Returns:
        [
            {
                "id": "c_0",           # child id
                "parent_id": "p_0",    # 所属 parent id
                "content": "...",       # 文本内容
                "level": "child",       # child | parent
                "index": 0,             # 在兄弟节点中的序号
            },
            ...
        ]
    """
    child_size = child_size or CHILD_SIZE
    child_overlap = child_overlap or CHILD_OVERLAP
    parent_size = parent_size or PARENT_SIZE
    parent_overlap = parent_overlap or PARENT_OVERLAP

    # 1. 先切 Parent chunks
    parents = _split_by_size(text, parent_size, parent_overlap)

    # 2. 每个 Parent 内切 Child chunks
    all_chunks = []
    for p_idx, parent_content in enumerate(parents):
        parent_id = "p_%d" % p_idx

        # Parent chunk
        all_chunks.append({
            "id": parent_id,
            "parent_id": parent_id,
            "content": parent_content,
            "level": "parent",
            "index": p_idx,
        })

        # Child chunks
        children = _split_by_size(parent_content, child_size, child_overlap)
        for c_idx, child_content in enumerate(children):
            if child_content.strip():
                all_chunks.append({
                    "id": "c_%d_%d" % (p_idx, c_idx),
                    "parent_id": parent_id,
                    "content": child_content,
                    "level": "child",
                    "index": c_idx,
                })

    return all_chunks


def get_child_chunks(chunks: list[dict]) -> list[dict]:
    """从分块结果中提取所有 child chunks（用于向量化）"""
    return [c for c in chunks if c["level"] == "child"]


def get_parent_context(chunks: list[dict], child_id: str,
                       neighbor_count: int = 1) -> str:
    """根据 child chunk id 获取完整的父上下文

    返回该 child 所属的 parent chunk，以及相邻的 parent chunks，
    确保 LLM 获得充足的上下文信息。

    Args:
        chunks: 完整分块结果
        child_id: 命中的 child chunk id
        neighbor_count: 额外包含的相邻 parent 数量

    Returns:
        拼接后的上下文字符串
    """
    # 找到 child → parent 映射
    parent_id = None
    for c in chunks:
        if c["id"] == child_id:
            parent_id = c["parent_id"]
            break

    if not parent_id:
        return ""

    # 收集相关 parent chunks
    parents = [c for c in chunks if c["level"] == "parent"]
    target_idx = None
    for i, p in enumerate(parents):
        if p["id"] == parent_id:
            target_idx = i
            break

    if target_idx is None:
        return ""

    # 取目标 parent + 前后邻居
    start = max(0, target_idx - neighbor_count)
    end = min(len(parents), target_idx + neighbor_count + 1)
    context_parents = parents[start:end]

    return "\n\n".join(p["content"] for p in context_parents)
