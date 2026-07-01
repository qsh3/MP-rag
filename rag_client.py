"""
RAGFlow 客户端 — 知识库引擎集成

核心能力（由 RAGFlow 提供）：
1. 多格式文档解析（PDF/DOCX/图片/Excel/PPT）+ 版面分析 + 智能分块
2. 向量存储 + Embedding
3. 混合检索（向量 + BM25 + Reranker）

RAGFlow 不可用时自动降级为本地模式（PyMuPDF + Qdrant + DashScope Embedding）。

启用方式：
    设置环境变量 RAGFLOW_BASE_URL 和 RAGFLOW_API_KEY，USE_RAGFLOW=1
"""

import time
from pathlib import Path
from typing import Optional

import requests

from config import (
    RAGFLOW_BASE_URL,
    RAGFLOW_API_KEY,
    TOP_K_RETRIEVAL,
)


class RAGFlowClient:
    """RAGFlow REST API 封装 — 知识库问答系统引擎"""

    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = base_url or RAGFLOW_BASE_URL
        self.api_key = api_key or RAGFLOW_API_KEY
        self._dataset_cache: dict[str, str] = {}

        # 自动检测连通性：配了地址就尝试连接，连不上自动降级
        if self.base_url and self.api_key:
            self._auth = {"Authorization": "Bearer %s" % self.api_key}
            self._api = "%s/api/v1" % self.base_url.rstrip("/")
            self.available = self._check_connection()
        else:
            self.available = False

        if self.available:
            print("[RAGFlow] 已连接: %s" % self.base_url)
        else:
            print("[RAGFlow] 不可用 → 自动降级为本地模式 (PyMuPDF + Qdrant)")

    def _check_connection(self) -> bool:
        """验证 RAGFlow 是否真正可达"""
        try:
            resp = requests.get("%s/datasets" % self._api, headers=self._auth, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def ensure_available(self) -> bool:
        """确保连接可用（已不可用时尝试重连）"""
        if self.available:
            return True
        if not self.base_url or not self.api_key:
            return False
        self._auth = {"Authorization": "Bearer %s" % self.api_key}
        self._api = "%s/api/v1" % self.base_url.rstrip("/")
        self.available = self._check_connection()
        if self.available:
            print("[RAGFlow] 重连成功: %s" % self.base_url)
        return self.available

    def ping(self) -> bool:
        """实时检测连通性（不走缓存，专供健康检查用）"""
        if not self.base_url or not self.api_key:
            return False
        return self._check_connection()

    @staticmethod
    def _get_field(data, key: str):
        """兼容 RAGFlow API 返回 data 为 dict 或 list 两种情况"""
        if isinstance(data, dict):
            return data.get(key)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            return data[0].get(key)
        return None

    @staticmethod
    def _extract_list(data) -> list:
        """兼容 RAGFlow API 返回的各种 data 格式，统一提取为 list"""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # data 可能是 {"docs": [...]} 或 {"id": "..."} (单个对象)
            for key in ("docs", "documents", "items"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # 单个对象包装为 list
            if "id" in data:
                return [data]
        return []

    # ══════════════════════════════════════════════════════════
    # 知识库管理（一个 dataset = 一个知识库）
    # ══════════════════════════════════════════════════════════

    def create_dataset(self, name: str, description: str = "",
                       chunk_method: str = "naive") -> Optional[str]:
        """创建知识库"""
        if not self.ensure_available():
            return None

        resp = requests.post(
            "%s/datasets" % self._api,
            headers=self._auth,
            json={"name": name, "description": description, "chunk_method": chunk_method},
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            ds_id = self._get_field(data, "id")
            if ds_id:
                self._dataset_cache[name] = ds_id
                print("[RAGFlow] 知识库已创建: %s (%s)" % (name, ds_id))
                return ds_id
        print("[RAGFlow] 创建知识库失败: %s" % resp.text)
        return None

    def get_or_create_dataset(self, name: str) -> Optional[str]:
        """获取已有知识库，不存在则创建"""
        if not self.ensure_available():
            return None
        if name in self._dataset_cache:
            return self._dataset_cache[name]

        resp = requests.get(
            "%s/datasets?name=%s" % (self._api, name), headers=self._auth
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            datasets = self._extract_list(data)
            for ds in datasets:
                if ds.get("name") == name:
                    self._dataset_cache[name] = ds["id"]
                    print("[RAGFlow] 使用已有知识库: %s (%s)" % (name, ds["id"]))
                    return ds["id"]

        return self.create_dataset(name)

    def delete_dataset(self, dataset_id: str) -> bool:
        """删除知识库及其所有文档"""
        if not self.ensure_available():
            return False

        resp = requests.delete(
            "%s/datasets/%s" % (self._api, dataset_id), headers=self._auth
        )
        ok = resp.status_code == 200
        if ok:
            # 清除缓存
            self._dataset_cache = {k: v for k, v in self._dataset_cache.items() if v != dataset_id}
            print("[RAGFlow] 知识库已删除: %s" % dataset_id)
        return ok

    def list_datasets(self) -> list[dict]:
        """列出所有知识库"""
        if not self.ensure_available():
            return []

        resp = requests.get("%s/datasets" % self._api, headers=self._auth)
        if resp.status_code == 200:
            return self._extract_list(resp.json().get("data", []))
        return []

    # ══════════════════════════════════════════════════════════
    # 文档管理
    # ══════════════════════════════════════════════════════════

    def upload_document(self, dataset_id: str, file_path: str,
                        wait: bool = True) -> dict:
        """上传文档到知识库

        RAGFlow 自动完成：解析 → 分块 → Embedding → 入库

        Args:
            dataset_id: 知识库 ID
            file_path: 文档路径（支持 PDF/DOCX/TXT/MD/JPG/PNG/Excel/PPT）
            wait: 是否等待解析完成

        Returns:
            {"doc_id": "...", "status": "completed|processing|error",
             "chunks": [...], "error": "..."}
        """
        if not self.ensure_available():
            return {"error": "RAGFlow 不可用", "raw_text": self._local_parse(file_path)}

        # 上传文件
        with open(file_path, "rb") as f:
            resp = requests.post(
                "%s/datasets/%s/documents" % (self._api, dataset_id),
                headers=self._auth,
                files={"file": f},
            )
        if resp.status_code != 200:
            return {"error": "上传失败: %s" % resp.text, "raw_text": self._local_parse(file_path)}

        data = resp.json().get("data", {})
        doc_id = self._get_field(data, "id")
        if not doc_id:
            return {"error": "上传返回无doc_id: %s" % resp.text[:200], "raw_text": self._local_parse(file_path)}
        filename = Path(file_path).name
        print("[RAGFlow] 文档已上传: %s (id=%s)" % (filename, doc_id))

        # 触发解析（RAGFlow 需要手动启动）
        self._start_parsing(dataset_id, doc_id)

        if not wait:
            return {"doc_id": doc_id, "status": "processing", "chunks": []}

        # 轮询等待解析完成（最多 60 秒）
        return self._wait_for_parsing(dataset_id, doc_id, file_path)

    def upload_batch(self, dataset_id: str, dir_path: str) -> list[dict]:
        """批量上传目录中的文档到知识库"""
        if not self.ensure_available():
            print("[RAGFlow] 不可用，批量上传跳过")
            return []

        supported = {".pdf", ".docx", ".doc", ".txt", ".md",
                     ".jpg", ".jpeg", ".png", ".bmp",
                     ".xlsx", ".xls", ".pptx", ".ppt", ".csv"}
        results = []
        for f in Path(dir_path).rglob("*"):
            if f.suffix.lower() in supported:
                result = self.upload_document(dataset_id, str(f), wait=False)
                result["filename"] = f.name
                results.append(result)

        print("[RAGFlow] 批量上传 %d 个文档" % len(results))
        return results

    def list_documents(self, dataset_id: str) -> list[dict]:
        """列出知识库中所有文档"""
        if not self.ensure_available():
            return []

        resp = requests.get(
            "%s/datasets/%s/documents" % (self._api, dataset_id),
            headers=self._auth,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            docs = self._extract_list(data)
            return [{"id": d.get("id", ""), "name": d.get("name", ""),
                     "status": "ready" if d.get("run") == "DONE" else "processing",
                     "chunk_count": d.get("chunk_count", 0),
                     "size": d.get("size", 0)} for d in docs]
        return []

    def get_document_status(self, dataset_id: str, doc_id: str) -> dict:
        """查询单个文档的处理状态"""
        if not self.ensure_available():
            return {"status": "unknown", "error": "RAGFlow 不可用"}

        # 通过文档列表接口查询状态（避免详情接口返回文件内容的问题）
        resp = requests.get(
            "%s/datasets/%s/documents" % (self._api, dataset_id),
            headers=self._auth,
        )
        if resp.status_code != 200:
            return {"status": "error", "error": resp.text}

        try:
            data = resp.json().get("data", {})
            docs = self._extract_list(data)
            for d in docs:
                if d.get("id") == doc_id:
                    run = d.get("run", "")
                    if run == "DONE":
                        st = "completed"
                    elif run == "FAIL":
                        st = "error"
                    else:
                        st = "processing"
                    return {
                        "id": doc_id,
                        "name": d.get("name", ""),
                        "status": st,
                        "chunk_count": d.get("chunk_count", 0),
                    }
            return {"id": doc_id, "status": "unknown", "name": "", "chunk_count": 0}
        except Exception as e:
            return {"id": doc_id, "status": "unknown", "name": "", "chunk_count": 0}

    def delete_document(self, dataset_id: str, doc_id: str) -> bool:
        """删除文档及其所有 chunks"""
        if not self.ensure_available():
            return False

        resp = requests.delete(
            "%s/datasets/%s/documents" % (self._api, dataset_id),
            headers=self._auth,
            json={"ids": [doc_id]},
        )
        ok = resp.status_code == 200
        if ok:
            print("[RAGFlow] 文档已删除: %s" % doc_id)
        return ok

    def get_document_chunks(self, dataset_id: str, doc_id: str) -> list[dict]:
        """获取文档的所有 chunks"""
        if not self.ensure_available():
            return []

        resp = requests.get(
            "%s/datasets/%s/documents/%s/chunks" % (self._api, dataset_id, doc_id),
            headers=self._auth,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            # chunks API 返回 {"chunks": [...], "doc": {...}}
            if isinstance(data, dict):
                chunks = data.get("chunks", [])
            else:
                chunks = self._extract_list(data)
            return [{"id": c.get("id", ""), "content": c.get("content", ""),
                     "metadata": c.get("metadata", {})} for c in chunks if isinstance(c, dict)]
        return []

    # ══════════════════════════════════════════════════════════
    # 语义检索（核心能力：RAGFlow retrieval API = 查询预处理 + 混合检索）
    # ══════════════════════════════════════════════════════════

    def search(self, dataset_id: str, query: str, top_k: int = None,
               document_ids: list[str] = None) -> list[dict]:
        """混合检索 — 使用 RAGFlow retrieval API

        服务端自动完成：
        1. 停用词过滤（rmWWW — 移除"如何""什么"等无意义疑问词）
        2. 词权重计算（IDF + NER 实体识别 + POS 词性加权）
        3. 同义词扩展
        4. 向量 + BM25 混合检索 + 融合重排序

        Args:
            document_ids: 限定检索的文档 ID 列表。None=不限，[]=无文档（返回空）。

        Returns:
            [{"content": "...", "score": 0.95, "doc_name": "...", "doc_id": "..."}, ...]
        """
        top_k = top_k or TOP_K_RETRIEVAL

        # 空列表 = 无权限文档，直接返回空结果
        if document_ids is not None and len(document_ids) == 0:
            return []

        if not self.ensure_available():
            return self._local_search(query, top_k, document_ids)

        body = {
            "question": query,
            "dataset_ids": [dataset_id],
            "top_k": top_k,
            "page": 1,
            "page_size": top_k,
            "similarity_threshold": 0.2,
            "vector_similarity_weight": 0.3,
        }
        if document_ids is not None:
            body["document_ids"] = document_ids

        resp = requests.post(
            "%s/retrieval" % self._api,
            headers=self._auth,
            json=body,
        )
        if resp.status_code != 200:
            return self._local_search(query, top_k, document_ids)

        body = resp.json()
        if body.get("code") != 0:
            return self._local_search(query, top_k, document_ids)

        data = body.get("data", {})
        chunks = data.get("chunks", [])
        return [{
            "content": c.get("content", ""),
            "score": c.get("similarity", 0),
            "doc_name": c.get("document_keyword", ""),
            "doc_id": c.get("document_id", ""),
        } for c in chunks if isinstance(c, dict)]

    # ══════════════════════════════════════════════════════════
    # 内部方法
    # ══════════════════════════════════════════════════════════

    def _start_parsing(self, dataset_id: str, doc_id: str):
        """触发 RAGFlow 开始解析文档"""
        try:
            resp = requests.post(
                "%s/datasets/%s/chunks" % (self._api, dataset_id),
                headers=self._auth,
                json={"document_ids": [doc_id]},
            )
            if resp.status_code == 200:
                print("[RAGFlow] 文档解析已启动: %s" % doc_id)
            else:
                print("[RAGFlow] 启动解析失败: %s" % resp.text[:100])
        except Exception as e:
            print("[RAGFlow] 启动解析异常: %s" % e)

    def _wait_for_parsing(self, dataset_id: str, doc_id: str, file_path: str) -> dict:
        """轮询等待 RAGFlow 完成文档解析"""
        for i in range(60):
            st = self.get_document_status(dataset_id, doc_id)
            if st.get("status") == "completed":
                chunks = self.get_document_chunks(dataset_id, doc_id)
                return {"doc_id": doc_id, "status": "completed",
                        "chunks": chunks, "total_chunks": len(chunks)}
            if st.get("status") == "error":
                return {"doc_id": doc_id, "status": "error",
                        "error": "RAGFlow 解析失败 (run=FAIL)", "raw_text": self._local_parse(file_path)}
            if st.get("status") == "unknown":
                # 文档可能还没出现在列表中，继续等待
                pass
            time.sleep(1)

        # 超时
        return {"doc_id": doc_id, "status": "timeout",
                "error": "解析超时", "raw_text": self._local_parse(file_path)}

    def _local_parse(self, file_path: str) -> str:
        """本地降级解析 — 纯文本提取"""
        suffix = Path(file_path).suffix.lower()

        if suffix == ".pdf":
            try:
                import fitz
                doc = fitz.open(file_path)
                raw = "\n".join(p.get_text().strip() for p in doc if p.get_text().strip())
                doc.close()
                return raw
            except Exception as e:
                return "[PDF解析错误: %s]" % e

        if suffix in (".docx", ".doc"):
            try:
                from docx import Document
                doc = Document(file_path)
                return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except Exception as e:
                return "[DOCX解析错误: %s]" % e

        if suffix in (".txt", ".md", ".csv"):
            return Path(file_path).read_text(encoding="utf-8", errors="replace")

        if suffix in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            return self._ocr_image(file_path)

        return "[不支持的文件格式: %s]" % suffix

    def _ocr_image(self, file_path: str) -> str:
        """图片 OCR — 使用 DashScope 视觉模型"""
        try:
            import base64
            from openai import OpenAI
            from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, QWEN_VL_MODEL

            with open(file_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()

            client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL)
            resp = client.chat.completions.create(
                model=QWEN_VL_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:image/%s;base64,%s" % (
                            Path(file_path).suffix[1:], img_b64)}},
                        {"type": "text", "text": "请提取并输出这张图片中的所有文字内容，保持原有格式和结构。只输出文字，不要额外说明。"},
                    ],
                }],
                max_tokens=4096,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return "[OCR错误: %s]" % e

    def _local_search(self, query: str, top_k: int,
                      document_ids: list[str] = None) -> list[dict]:
        """本地降级检索 — Qdrant ANN 搜索（支持文档级过滤）"""
        # 空列表 = 无权限文档，直接返回空
        if document_ids is not None and len(document_ids) == 0:
            return []

        try:
            from openai import OpenAI
            from qdrant_client import QdrantClient
            from qdrant_client.models import Filter, FieldCondition, MatchAny
            from config import (
                QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION,
                EMBED_API_KEY, EMBED_BASE_URL, EMBED_MODEL_NAME,
            )

            # 1. Embedding
            client = OpenAI(api_key=EMBED_API_KEY, base_url=EMBED_BASE_URL)
            emb_resp = client.embeddings.create(model=EMBED_MODEL_NAME, input=query)
            query_vector = emb_resp.data[0].embedding

            # 2. Qdrant 搜索（带文档级过滤）
            qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            query_filter = None
            if document_ids is not None:
                query_filter = Filter(
                    must=[FieldCondition(key="doc_id", match=MatchAny(any=document_ids))]
                )
            results = qdrant.search(
                collection_name=QDRANT_COLLECTION,
                query_vector=query_vector,
                limit=top_k,
                query_filter=query_filter,
            )
            return [{
                "content": r.payload.get("text", ""),
                "score": r.score,
                "doc_name": r.payload.get("filename", ""),
                "doc_id": r.payload.get("doc_id", ""),
                "chunk_id": r.id,
            } for r in results]
        except Exception as e:
            print("[本地检索错误: %s]" % e)
            return []


# ═══════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════

_client: Optional[RAGFlowClient] = None


def get_client() -> RAGFlowClient:
    """获取 RAGFlow 客户端单例"""
    global _client
    if _client is None:
        _client = RAGFlowClient()
    return _client
