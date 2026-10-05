"""可选大模型客户端（OpenAI 兼容接口）。

设计要点（严格遵守任务约束）：
- API Key **只从环境变量读取**（OPENAI_API_KEY 等），绝不写入源代码，也不提交仓库
  （见 .env.example 与 .gitignore）。
- 未配置 Key 时 is_available() 返回 False，所有调用自动回退到规则版，不影响任何
  基础功能（数据清洗 / 竞品分析 / 规则主题洞察照常运行）。
- 大模型输出一律视为**辅助性、待验证**内容；本模块不在任何地方把模型推测表述为
  已验证的市场事实。
- openai 为可选依赖：仅在真正调用时才 import，未安装时不报错（基础功能不依赖它）。
"""
from __future__ import annotations

import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# 环境变量名（可覆盖，便于指向兼容网关 / 本地模型）
ENV_KEY = "OPENAI_API_KEY"
ENV_BASE = "OPENAI_BASE_URL"
ENV_MODEL = "OPENAI_MODEL"

# 为防止演示时单次分析发起过多远程调用，限制 LLM 增强的最大评价条数
MAX_LLM_REVIEWS = 200


def is_available() -> bool:
    """是否已配置可用的 API Key。"""
    return bool(os.getenv(ENV_KEY))


def _model() -> str:
    return os.getenv(ENV_MODEL) or "gpt-4o-mini"


def _client():
    """惰性创建 OpenAI 客户端；未安装依赖或缺少 Key 时抛异常由调用方捕获。"""
    from openai import OpenAI
    return OpenAI(
        api_key=os.getenv(ENV_KEY),
        base_url=os.getenv(ENV_BASE) or None,
    )


def _chat(system: str, user: str, max_tokens: int = 600, temperature: float = 0.2):
    client = _client()
    resp = client.chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# 以下三个函数都在"有 Key 且调用方显式启用"时调用；任何异常都应由调用方回退规则版。
# ---------------------------------------------------------------------------

def llm_sentiment(text: str) -> str:
    """用大模型判断单条评价情感，返回 positive/negative/neutral。

    失败时由调用方回退到 src.sentiment.label（规则版）。
    """
    sys_p = (
        "你是中文电商评论情感标注助手。只输出一个词：positive、negative 或 neutral。"
        "依据整句语气判断，不解释。"
    )
    out = _chat(sys_p, text, max_tokens=8, temperature=0.0).strip().lower()
    for tok in ("positive", "negative", "neutral"):
        if tok in out:
            return tok
    return "neutral"


def llm_themes(text: str, theme_names: list[str]) -> list[str]:
    """用大模型从给定主题清单中为单条评价打标，返回命中的主题名列表。

    失败或解析异常时由调用方回退到规则版 classify。
    """
    sys_p = (
        "你是中文产品评论主题标注助手。给定主题清单，判断评论命中哪些主题。"
        "只输出 JSON 数组，例如 [\"容量/续航\",\"价格\"]，不要解释。"
    )
    user_p = f"主题清单：{theme_names}\n评论：{text}"
    out = _chat(sys_p, user_p, max_tokens=200, temperature=0.0)
    try:
        arr = json.loads(out)
        if isinstance(arr, list):
            valid = set(theme_names)
            return [t for t in arr if t in valid]
    except Exception:
        pass
    return []


def llm_opportunity_narrative(hypo_title: str, hypo_detail: str,
                              ctx_summary: str) -> str:
    """用大模型为一条机会假设生成更自然的表述（仍为待验证假设，不声称已证实）。

    失败或异常时由调用方保留规则版 detail。
    """
    sys_p = (
        "你是市场研究助手。下面是一条基于规则统计得到的『待验证机会假设』，"
        "请用更清晰、专业的中文重写其描述，强调它仍是假设、需要验证。"
        "不要新增任何数据点，不要把它说成已证实的市场结论。只输出重写后的段落。"
    )
    user_p = (
        f"假设标题：{hypo_title}\n"
        f"原始统计描述：{hypo_detail}\n"
        f"上下文（市场概览）：{ctx_summary}"
    )
    return _chat(sys_p, user_p, max_tokens=500, temperature=0.3).strip()
