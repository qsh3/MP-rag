"""
LLM 服务 — DeepSeek 调用封装（支持流式生成）
"""
import re
from typing import Generator

from openai import OpenAI

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT,
)

# 全局单例
_llm: OpenAI = None


def get_llm() -> OpenAI:
    global _llm
    if _llm is None:
        _llm = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            timeout=LLM_TIMEOUT,
        )
    return _llm


# ── RAG 系统提示词 ─────────────────────────────────────

RAG_SYSTEM_PROMPT = """你是一个企业知识库智能助手。你的回答基于提供的文档内容。

回答规则：
1. 仅基于提供的【参考文档】内容回答，不编造任何信息
2. 如果文档中没有相关信息，明确告知用户"文档中未找到相关信息"
3. 引用信息时注明来源文档名称
4. 回答要专业、准确、简洁，使用中文
5. 如果文档内容存在矛盾，指出矛盾并给出不同来源的说法
6. 对于列举型问题，使用结构化格式（列表/表格）回答"""


# ── 核心方法 ───────────────────────────────────────────

def generate(messages: list[dict], temperature: float = 0.3,
             stream: bool = False, seed: int = 42,
             model: str = None) -> str | Generator:
    """通用 LLM 调用"""
    kwargs = dict(
        model=model or LLM_MODEL,
        temperature=temperature,
        messages=messages,
        stream=stream,
        seed=seed,
    )
    if stream:
        return get_llm().chat.completions.create(**kwargs)
    else:
        resp = get_llm().chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


def generate_json(messages: list[dict], temperature: float = 0.2,
                  seed: int = 42, model: str = None) -> str:
    """JSON 模式调用 + markdown 代码块自动清洗"""
    kwargs = dict(
        model=model or LLM_MODEL,
        temperature=temperature,
        messages=messages,
        response_format={"type": "json_object"},
        seed=seed,
    )
    resp = get_llm().chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or "{}"
    # 清洗 markdown 包裹
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    return content


def generate_rag_stream(context: str, question: str, history: str = ""):
    """RAG 流式生成（支持多轮对话）

    Yields:
        str: 每次 yield 一个文本片段
    """
    history_block = ""
    if history:
        history_block = f"""## 对话历史

{history}

"""

    user_prompt = f"""{history_block}## 参考文档

{context}

## 用户问题

{question}

请根据参考文档回答用户问题。如果问题与文档内容无关，请如实说明。"""

    stream = generate(
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        stream=True,
    )

    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
