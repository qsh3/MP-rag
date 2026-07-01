"""
文档管理 API — 上传/列表/删除
"""
import os
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from models.schemas import DocResponse, DocListResponse
from services import kb_service
from rag_client import get_client as get_rag_client
from config import UPLOAD_DIR
from api.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/kb/{kb_id}/docs", tags=["文档"])


@router.post("")
async def upload_documents(kb_id: str, files: list[UploadFile] = File(...), current_user=Depends(get_current_user)):
    """上传文档到知识库（支持多文件）"""
    kb = kb_service.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    rag = get_rag_client()
    dataset_id = kb.get("ragflow_dataset_id")
    results = []

    for f in files:
        # 保存到本地
        kb_upload_dir = UPLOAD_DIR / kb_id
        kb_upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = kb_upload_dir / f.filename

        content = await f.read()
        file_path.write_bytes(content)

        file_type = Path(f.filename).suffix.lower().lstrip(".")
        file_size = len(content)

        # 创建 MySQL 记录
        doc = kb_service.add_document(
            kb_id, f.filename, file_type, file_size, str(file_path)
        )

        # 上传到 RAGFlow（wait=False 不阻塞，后台解析）
        status_msg = ""
        ragflow_doc_id = ""
        try:
            if rag.available and dataset_id:
                result = rag.upload_document(dataset_id, str(file_path), wait=False)

                if "error" in result:
                    kb_service.update_document_status(
                        doc["id"], "error",
                        error_message=result.get("error", "未知错误")
                    )
                    status_msg = "上传失败: %s" % result.get("error", "")
                else:
                    ragflow_doc_id = result.get("doc_id", "")
                    kb_service.update_document_status(
                        doc["id"], "processing",
                        ragflow_doc_id=ragflow_doc_id,
                        chunk_count=0,
                    )
                    status_msg = "已上传，RAGFlow 后台解析中..."
            else:
                kb_service.update_document_status(doc["id"], "ready", chunk_count=0)
                status_msg = "已保存（RAGFlow 离线）"
        except Exception as e:
            kb_service.update_document_status(doc["id"], "error", error_message=str(e))
            status_msg = "异常: %s" % str(e)[:100]

        doc_updated = kb_service.get_document(doc["id"])
        results.append(DocResponse(**doc_updated))

    if not results:
        raise HTTPException(status_code=400, detail="未上传任何文件")

    # 检查是否有失败的
    errors = [r for r in results if r.status == "error"]
    if errors:
        names = ", ".join(r.filename for r in errors)
        raise HTTPException(status_code=500, detail="%s 上传失败，请查看文档列表了解详情" % names)

    return {
        "message": "上传 %d 个文档 %s" % (len(results), status_msg),
        "results": [r.model_dump() for r in results],
    }


@router.get("", response_model=DocListResponse)
def list_documents(kb_id: str, current_user=Depends(get_current_user)):
    """列出知识库中的文档"""
    kb = kb_service.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    docs = kb_service.list_documents(kb_id)
    return DocListResponse(total=len(docs), items=[DocResponse(**d) for d in docs])


@router.get("/{doc_id}", response_model=DocResponse)
def get_document(kb_id: str, doc_id: str, current_user=Depends(get_current_user)):
    """获取文档详情"""
    doc = kb_service.get_document(doc_id)
    if not doc or doc["kb_id"] != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    return DocResponse(**doc)


@router.delete("/{doc_id}")
def delete_document(kb_id: str, doc_id: str, current_user=Depends(get_current_user)):
    """删除文档及其 chunks"""
    doc = kb_service.get_document(doc_id)
    if not doc or doc["kb_id"] != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")

    ok = kb_service.delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=500, detail="删除失败")
    return {"message": "已删除"}
