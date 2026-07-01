"""
评估 API
"""
from fastapi import APIRouter, HTTPException, Query

from models.schemas import EvalRunRequest, EvalReviewRequest, EvalReportResponse, EvalMetric, ReviewDetail
from services import kb_service
from evaluation.runner import run_ragas_evaluation, run_review
from evaluation.collector import collect_from_history, get_evaluated_scores, get_scored_details, clear_evaluation_records

router = APIRouter(prefix="/api/v1/eval", tags=["评估"])


@router.post("/run", response_model=EvalReportResponse)
def run_evaluation(req: EvalRunRequest):
    """运行 RAGAS 评估（不含复审，复审需单独调用 /review）"""
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

    metrics = [EvalMetric(name=m["name"], score=m["score"], description=m["description"])
               for m in result["metrics"]]

    return EvalReportResponse(
        kb_id=req.kb_id,
        kb_name=kb.get("name", ""),
        sample_count=result["sample_count"],
        metrics=metrics,
        new_evaluated=result.get("new_evaluated", 0),
        created_at="",
    )


@router.post("/review", response_model=EvalReportResponse)
def run_review_endpoint(req: EvalReviewRequest):
    """对已评估记录运行跨厂商复审"""
    kb = kb_service.get_kb(req.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    result = run_review(req.kb_id, max_samples=req.max_samples)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    # 构建指标（含复审分数）
    metrics = []
    for m in result["metrics"]:
        review_score = None
        if result.get("review") and result["review"].get("avg_review_scores"):
            review_score = result["review"]["avg_review_scores"].get(m["name"])
        metrics.append(EvalMetric(
            name=m["name"], score=m["score"], description=m["description"],
            review_score=review_score,
        ))

    review_detail = None
    if result.get("review"):
        r = result["review"]
        review_detail = ReviewDetail(
            reviewed=True,
            review_status="ok",
            reviewed_count=r.get("reviewed_count", 0),
            avg_review_scores=r.get("avg_review_scores", {}),
            reason=f"复审完成，共 {r.get('reviewed_count', 0)} 条",
            adjustments=[],
        )

    return EvalReportResponse(
        kb_id=req.kb_id,
        kb_name=kb.get("name", ""),
        sample_count=result.get("reviewed_count", 0),
        metrics=metrics,
        created_at="",
        review=review_detail,
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

    # 聚合复审分数
    rfaith_vals = [s["review_faithfulness"] for s in scored if s.get("review_faithfulness") is not None and s["review_faithfulness"] >= 0]
    rrelev_vals = [s["review_answer_relevancy"] for s in scored if s.get("review_answer_relevancy") is not None and s["review_answer_relevancy"] >= 0]
    rprec_vals = [s["review_context_precision"] for s in scored if s.get("review_context_precision") is not None and s["review_context_precision"] >= 0]
    reviewed_count = sum(1 for s in scored if s.get("reviewed") == 1)

    metrics = []
    if faith_vals:
        metrics.append(EvalMetric(
            name="faithfulness", score=round(sum(faith_vals) / len(faith_vals), 4),
            description="答案中的断言是否可追溯到检索文档（0-1，越高越好）",
            review_score=round(sum(rfaith_vals) / len(rfaith_vals), 4) if rfaith_vals else None,
        ))
    if relev_vals:
        metrics.append(EvalMetric(
            name="answer_relevancy", score=round(sum(relev_vals) / len(relev_vals), 4),
            description="答案是否直接回答了问题、不偏题（0-1，越高越好）",
            review_score=round(sum(rrelev_vals) / len(rrelev_vals), 4) if rrelev_vals else None,
        ))
    if prec_vals:
        metrics.append(EvalMetric(
            name="context_precision", score=round(sum(prec_vals) / len(prec_vals), 4),
            description="检索到的文档片段中真正有用的占比（0-1，越高越好）",
            review_score=round(sum(rprec_vals) / len(rprec_vals), 4) if rprec_vals else None,
        ))

    # 构建复审详情
    review_detail = None
    if reviewed_count > 0:
        review_detail = ReviewDetail(
            reviewed=True,
            review_status="ok",
            reviewed_count=reviewed_count,
            avg_review_scores={
                "faithfulness": round(sum(rfaith_vals) / len(rfaith_vals), 4) if rfaith_vals else 0,
                "answer_relevancy": round(sum(rrelev_vals) / len(rrelev_vals), 4) if rrelev_vals else 0,
                "context_precision": round(sum(rprec_vals) / len(rprec_vals), 4) if rprec_vals else 0,
            },
            reason=f"已复审 {reviewed_count} 条",
            adjustments=[],
        )

    return EvalReportResponse(
        kb_id=kb_id,
        kb_name=kb.get("name", ""),
        sample_count=len(scored),
        metrics=metrics,
        created_at=scored[0].get("created_at", ""),
        review=review_detail,
    )


@router.get("/data/{kb_id}")
def get_eval_data(kb_id: str, limit: int = Query(50, ge=1, le=200)):
    """获取评估原始数据（用于前端展示）"""
    kb = kb_service.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    data = collect_from_history(kb_id, limit)
    return {"total": len(data), "items": data}


@router.get("/details/{kb_id}")
def get_eval_details(kb_id: str, limit: int = Query(20, ge=1, le=100)):
    """获取已评估记录的详细推理过程（含评估者拆解声明、判定、复审理由等）"""
    kb = kb_service.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    data = get_scored_details(kb_id, limit)
    return {"total": len(data), "items": data}


@router.delete("/records/{kb_id}")
def clear_eval_records(kb_id: str):
    """清空指定知识库的所有评估记录"""
    kb = kb_service.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    count = clear_evaluation_records(kb_id)
    return {"kb_id": kb_id, "deleted": count, "message": f"已清空 {count} 条评估记录"}
