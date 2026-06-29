"""
评估 API
"""
from fastapi import APIRouter, HTTPException, Query

from models.schemas import EvalRunRequest, EvalReportResponse, EvalMetric
from services import kb_service
from evaluation.runner import run_ragas_evaluation
from evaluation.collector import collect_from_history, get_evaluated_scores

router = APIRouter(prefix="/api/v1/eval", tags=["评估"])


@router.post("/run", response_model=EvalReportResponse)
def run_evaluation(req: EvalRunRequest):
    """运行 RAGAS 评估"""
    kb = kb_service.get_kb(req.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    result = run_ragas_evaluation(req.kb_id, req.test_questions, max_samples=req.max_samples)

    if result.get("error"):
        return EvalReportResponse(
            kb_id=req.kb_id,
            kb_name=kb.get("name", ""),
            sample_count=result["sample_count"],
            metrics=[EvalMetric(name="error", score=0, description=result["error"])],
            new_evaluated=0,
            created_at="",
        )

    return EvalReportResponse(
        kb_id=req.kb_id,
        kb_name=kb.get("name", ""),
        sample_count=result["sample_count"],
        metrics=[EvalMetric(**m) for m in result["metrics"]],
        new_evaluated=result.get("new_evaluated", 0),
        created_at="",
    )


@router.get("/report/{kb_id}", response_model=EvalReportResponse)
def get_report(kb_id: str):
    """查看最近的评估报告（从数据库读取已保存的评分）"""
    kb = kb_service.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    # 从数据库读取已有评分
    scored = get_evaluated_scores(kb_id, limit=100)

    if not scored:
        return EvalReportResponse(
            kb_id=kb_id,
            kb_name=kb.get("name", ""),
            sample_count=0,
            metrics=[],
            created_at="",
        )

    # 聚合评分
    faith_vals = [s["faithfulness"] for s in scored if s["faithfulness"] is not None and s["faithfulness"] >= 0]
    relev_vals = [s["answer_relevancy"] for s in scored if s["answer_relevancy"] is not None and s["answer_relevancy"] >= 0]
    prec_vals = [s["context_precision"] for s in scored if s["context_precision"] is not None and s["context_precision"] >= 0]

    metrics = []
    if faith_vals:
        metrics.append(EvalMetric(
            name="faithfulness", score=round(sum(faith_vals) / len(faith_vals), 4),
            description="答案中的断言是否可追溯到检索文档（0-1，越高越好）"
        ))
    if relev_vals:
        metrics.append(EvalMetric(
            name="answer_relevancy", score=round(sum(relev_vals) / len(relev_vals), 4),
            description="答案是否直接回答了问题、不偏题（0-1，越高越好）"
        ))
    if prec_vals:
        metrics.append(EvalMetric(
            name="context_precision", score=round(sum(prec_vals) / len(prec_vals), 4),
            description="检索到的文档片段中真正有用的占比（0-1，越高越好）"
        ))

    return EvalReportResponse(
        kb_id=kb_id,
        kb_name=kb.get("name", ""),
        sample_count=len(scored),
        metrics=metrics,
        created_at=scored[0].get("created_at", ""),
    )


@router.get("/data/{kb_id}")
def get_eval_data(kb_id: str, limit: int = Query(50, ge=1, le=200)):
    """获取评估原始数据（用于前端展示）"""
    kb = kb_service.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    data = collect_from_history(kb_id, limit)
    return {"total": len(data), "items": data}
