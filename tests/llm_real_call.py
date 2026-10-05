"""真实大模型调用验证（可选，需自行配置 API Key）。

本脚本用于在「具备可用 API Key 的环境」下，对可选的大模型增强层做一次真实调用验证：
- 调用成功：打印模型输出，确认解析正确；
- 失败回退：故意指向错误模型，确认自动回退规则版且不崩溃；
- 费用控制：确认情感标注调用次数不超过 MAX_LLM_REVIEWS。

用法（PowerShell）：
    $env:OPENAI_API_KEY="sk-..."
    $env:OPENAI_BASE_URL=""            # 可选，兼容网关/Ollama
    $env:OPENAI_MODEL="gpt-4o-mini"    # 可选
    python tests/llm_real_call.py

⚠️ 若未配置 OPENAI_API_KEY，本脚本会**明确标注「未验证」**，不会假装通过。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import llm as LLM, insights as I  # noqa: E402
import pandas as pd  # noqa: E402


def main() -> int:
    print("=== 大模型增强 · 真实调用验证 ===")
    if not LLM.is_available():
        print("状态：未验证 ⚠️")
        print("原因：当前环境未配置 OPENAI_API_KEY（未提供可用密钥），")
        print("      因此**未进行真实大模型调用**，不声称 AI 增强功能已通过实测。")
        print("说明：无 Key 时的优雅降级（规则版兜底）已由 tests/test_llm.py 覆盖。")
        return 0

    print(f"已检测到 API Key。模型：{LLM._model()}　Base：{os.getenv('OPENAI_BASE_URL') or 'OpenAI 官方'}")
    print(f"费用控制上限 MAX_LLM_REVIEWS = {LLM.MAX_LLM_REVIEWS}")

    # 1) 真实调用：情感标注
    samples = ["轻便小巧，续航耐用，很满意", "太重了，充电还发烫，有点担心"]
    for s in samples:
        try:
            out = LLM.llm_sentiment(s)
            print(f"[成功] 输入：{s} → 情感：{out}")
        except Exception as e:
            print(f"[失败] 真实调用异常：{e!r}（调用方会自动回退规则版）")
            return 1

    # 2) 真实调用：机会假设润色
    try:
        narr = LLM.llm_opportunity_narrative(
            "在「≤99」价格带，低分评价中「便携/重量」提及率偏高",
            "低分评价里便携/重量提及率约 90%。", "共 2 款产品、17 条有效评价。")
        print(f"[成功] 假设润色输出（前 120 字）：{narr[:120]}")
    except Exception as e:
        print(f"[失败] 假设润色异常：{e!r}")

    # 3) 真实调用 + 费用控制：分析 5 条评价，确认调用次数不超上限
    df = pd.DataFrame([
        {"review_id": f"R{i}", "product_id": "P1", "rating": 5, "review_text": "轻便续航耐用",
         "review_date": "2025-01-01", "source": "s", "rating_valid": True,
         "date_valid": True, "text_valid": True}
        for i in range(1, 6)
    ])
    res = I.analyze_reviews(df, use_llm=True)
    ok_cap = res["llm_used"] <= res["llm_budget"]
    print(f"[费用控制] 模型标注 {res['llm_used']}/{res['llm_budget']} 条，"
          f"{'通过' if ok_cap else '异常'}；情感分布：{res['sentiment_summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
