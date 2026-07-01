"""
LLM 服务 — DeepSeek 调用封装（支持流式生成）
"""
import re
from typing import Generator

from openai import OpenAI

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    KIMI_API_KEY,
    KIMI_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT,
)

# 多厂商客户端缓存
_clients: dict[str, OpenAI] = {}


def get_llm(provider: str = "deepseek") -> OpenAI:
    """获取指定厂商的 LLM 客户端（单例缓存）

    Args:
        provider: 厂商名 — "deepseek" | "dashscope" | "kimi"
    """
    global _clients
    if provider not in _clients:
        if provider == "deepseek":
            _clients[provider] = OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
                timeout=LLM_TIMEOUT,
            )
        elif provider == "dashscope":
            _clients[provider] = OpenAI(
                api_key=DASHSCOPE_API_KEY,
                base_url=DASHSCOPE_BASE_URL,
                timeout=LLM_TIMEOUT,
            )
        elif provider == "kimi":
            _clients[provider] = OpenAI(
                api_key=KIMI_API_KEY,
                base_url=KIMI_BASE_URL,
                timeout=LLM_TIMEOUT,
            )
        else:
            raise ValueError(f"未知的 LLM 厂商: {provider}，支持: deepseek, dashscope, kimi")
    return _clients[provider]


# ── RAG 系统提示词 ─────────────────────────────────────

RAG_SYSTEM_PROMPT = """你是一个知识库智能助手。你的回答基于提供的文档内容。

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
             model: str = None, provider: str = "deepseek") -> str | Generator:
    """通用 LLM 调用

    Args:
        provider: 厂商名 — "deepseek"（默认）| "dashscope" | "kimi"
    """
    kwargs = dict(
        model=model or LLM_MODEL,
        temperature=temperature,
        messages=messages,
        stream=stream,
        seed=seed,
    )
    if stream:
        return get_llm(provider).chat.completions.create(**kwargs)
    else:
        resp = get_llm(provider).chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


def generate_json(messages: list[dict], temperature: float = 0.2,
                  seed: int = 42, model: str = None,
                  provider: str = "deepseek") -> str:
    """JSON 模式调用 + markdown 代码块自动清洗

    Args:
        provider: 厂商名 — "deepseek"（默认）| "dashscope" | "kimi"
    """
    kwargs = dict(
        model=model or LLM_MODEL,
        temperature=temperature,
        messages=messages,
        response_format={"type": "json_object"},
        seed=seed,
    )
    resp = get_llm(provider).chat.completions.create(**kwargs)
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
