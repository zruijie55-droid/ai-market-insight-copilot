"""大模型客户端测试：无 Key 时优雅降级（不报错、不联网）。

注意：本测试环境未配置 OPENAI_API_KEY，重点验证：
- is_available() 返回 False；
- insights 在 use_llm=True 但无 Key 时仍可用规则兜底完成分析。
"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from src import llm as LLM, insights as I


class TestLLMFallback(unittest.TestCase):
    def test_no_key_unavailable(self):
        self.assertFalse(LLM.is_available())

    def test_insights_llm_flag_without_key_falls_back(self):
        # 无 Key 时 use_llm=True 不应报错，应回退规则完成分析
        df = pd.DataFrame([
            {"review_id": "R1", "product_id": "P1", "rating": 2, "review_text": "太重了还发烫",
             "review_date": "2025-01-01", "source": "s", "rating_valid": True,
             "date_valid": True, "text_valid": True},
            {"review_id": "R2", "product_id": "P1", "rating": 5, "review_text": "轻便续航耐用",
             "review_date": "2025-01-01", "source": "s", "rating_valid": True,
             "date_valid": True, "text_valid": True},
        ])
        res = I.analyze_reviews(df, use_llm=True)
        self.assertEqual(res["n_text"], 2)
        self.assertFalse(res["use_llm"])  # 实际未启用（无 Key 自动回退）
        self.assertIn("便携/重量", set(res["text_reviews"].iloc[0]["themes"]))


def _df(n: int) -> pd.DataFrame:
    return pd.DataFrame([
        {"review_id": f"R{i}", "product_id": "P1", "rating": 5, "review_text": "轻便续航耐用",
         "review_date": "2025-01-01", "source": "s", "rating_valid": True,
         "date_valid": True, "text_valid": True}
        for i in range(1, n + 1)
    ])


class TestLLMCostControl(unittest.TestCase):
    """用 mock 替换大模型客户端，验证「费用控制 / 失败回退」逻辑（非真实模型调用）。

    说明：本组测试通过 monkeypatch 模拟「已配置 Key」的场景，用于验证：
    - 情感标注的模型调用次数受 MAX_LLM_REVIEWS 上限约束（费用控制）；
    - 模型调用抛错时自动回退规则版，不使整条分析崩溃。
    真实大模型调用的验证见 tests/llm_real_call.py（需配置 Key，否则标注为未验证）。
    """

    def setUp(self):
        self._orig_avail = LLM.is_available
        self._orig_sent = LLM.llm_sentiment
        self._orig_max = LLM.MAX_LLM_REVIEWS

    def tearDown(self):
        LLM.is_available = self._orig_avail
        LLM.llm_sentiment = self._orig_sent
        LLM.MAX_LLM_REVIEWS = self._orig_max

    def test_llm_call_cap_enforced(self):
        calls = {"n": 0}
        LLM.is_available = lambda: True
        LLM.MAX_LLM_REVIEWS = 3

        def fake_sentiment(text):
            calls["n"] += 1
            return "neutral"

        LLM.llm_sentiment = fake_sentiment
        res = I.analyze_reviews(_df(10), use_llm=True)
        self.assertEqual(calls["n"], 3, "大模型情感标注调用次数必须受 MAX_LLM_REVIEWS 限制")
        self.assertEqual(res["llm_used"], 3)
        self.assertEqual(res["llm_budget"], 3)
        self.assertTrue(res["use_llm"])
        self.assertEqual(res["n_text"], 10)  # 其余回退规则版，样本不丢

    def test_llm_failure_falls_back(self):
        LLM.is_available = lambda: True

        def boom(text):
            raise RuntimeError("模拟 API 失败")

        LLM.llm_sentiment = boom
        res = I.analyze_reviews(_df(2), use_llm=True)
        # 异常被捕获并回退规则版，分析不崩溃
        self.assertEqual(res["n_text"], 2)
        self.assertTrue(res["use_llm"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
