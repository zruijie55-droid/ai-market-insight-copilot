"""F3/F4 洞察与假设测试：单条多主题、未命中、空文本、评分分层、零分母、证据、假设不崩溃。"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from src import insights as I
from src.analysis import DEFAULT_BANDS

ORDER = [b[2] for b in DEFAULT_BANDS]


def _df(texts, ratings):
    return pd.DataFrame([
        {"review_id": f"R{i}", "product_id": "P1", "rating": r, "review_text": t,
         "review_date": "2025-01-01", "source": "s",
         "rating_valid": (1 <= r <= 5), "date_valid": True, "text_valid": bool(str(t).strip())}
        for i, (t, r) in enumerate(zip(texts, ratings), 1)
    ])


class TestInsights(unittest.TestCase):
    def test_single_review_multi_theme(self):
        df = _df(["轻便小巧，容量大续航耐用，充电快"], [5])
        res = I.analyze_reviews(df)
        themes = set(res["text_reviews"].iloc[0]["themes"])
        self.assertIn("便携/重量", themes)
        self.assertIn("容量/续航", themes)
        self.assertIn("充电速度", themes)

    def test_unmatched(self):
        df = _df(["物流很快客服态度好"], [5])
        res = I.analyze_reviews(df)
        self.assertEqual(res["unmatched"], 1)

    def test_empty_text_excluded(self):
        df = _df(["", "轻便"], [5, 4])
        res = I.analyze_reviews(df)
        self.assertEqual(res["n_text"], 1)

    def test_rating_layers(self):
        df = _df(["太重了", "容量大续航耐用", "轻便"], [2, 5, 4])
        res = I.analyze_reviews(df)
        by = {t["theme"]: t for t in res["theme_stats"]}
        self.assertEqual(by["便携/重量"]["low"], 1)
        self.assertEqual(by["便携/重量"]["high"], 1)
        self.assertEqual(by["容量/续航"]["high"], 1)

    def test_zero_denominator(self):
        df = pd.DataFrame(columns=["review_id", "product_id", "rating", "review_text",
                                   "review_date", "source", "rating_valid",
                                   "date_valid", "text_valid"])
        res = I.analyze_reviews(df)
        self.assertEqual(res["n_text"], 0)
        self.assertEqual(res["theme_stats"][0]["pct"], 0.0)

    def test_evidence(self):
        df = _df(["太重了", "轻便"], [2, 4])
        res = I.analyze_reviews(df)
        ev = I.evidence_for(res["text_reviews"], "便携/重量")
        self.assertEqual(len(ev), 2)

    def test_hypotheses_no_crash(self):
        df = _df(["太重了", "容量大", "轻便"], [2, 5, 4])
        merged = pd.DataFrame([
            {"review_id": f"R{i}", "product_id": "P1", "rating": r,
             "price_band": "≤99", "rating_valid": True}
            for i, r in enumerate([2, 5, 4], 1)])
        res = I.analyze_reviews(df)
        hypos = I.build_hypotheses(merged, res["text_reviews"], ORDER)
        self.assertIsInstance(hypos, list)
        self.assertTrue(len(hypos) >= 1)

    def test_monthly_trend(self):
        df = _df(["轻便好用", "太重了", "容量不错"], [5, 2, 4])
        df["review_date"] = pd.to_datetime(["2025-01-03", "2025-01-20", "2025-02-01"])
        res = I.analyze_reviews(df)

        self.assertEqual(res["time_summary"]["n_dated"], 3)
        self.assertEqual(res["time_summary"]["n_months"], 2)
        self.assertEqual([m["month"] for m in res["monthly_trend"]],
                         ["2025-01", "2025-02"])
        self.assertEqual(res["monthly_trend"][0]["reviews"], 2)
        self.assertEqual(res["monthly_trend"][0]["neg_rate"], 50.0)
        self.assertEqual(res["monthly_trend"][0]["avg_rating"], 3.5)

    def test_monthly_trend_excludes_invalid_dates(self):
        df = _df(["轻便", "太重"], [5, 2])
        df["review_date"] = pd.to_datetime(["2025-01-03", None])
        df["date_valid"] = [True, False]
        res = I.analyze_reviews(df)

        self.assertEqual(res["time_summary"]["n_dated"], 1)
        self.assertEqual(len(res["monthly_trend"]), 1)

    def test_brand_feedback_summary_and_matrix(self):
        products = pd.DataFrame([
            {"product_id": "P1", "brand": "A"},
            {"product_id": "P2", "brand": "B"},
        ])
        reviews = pd.concat([
            _df(["轻便好用", "太重了", "不错"], [5, 2, 4]),
            _df(["容量耐用", "发热严重", "价格实惠"], [5, 1, 5])
              .assign(product_id="P2", review_id=["R4", "R5", "R6"]),
        ], ignore_index=True)
        insight = I.analyze_reviews(reviews)
        result = I.analyze_brand_feedback(products, insight["text_reviews"], min_reviews=3)

        self.assertEqual(result["linked_reviews"], 6)
        self.assertEqual(result["eligible_brands"], 2)
        by_brand = {row["brand"]: row for row in result["summary"]}
        self.assertEqual(by_brand["A"]["reviews"], 3)
        self.assertEqual(by_brand["A"]["neg_rate"], 33.3)
        self.assertEqual({row["brand"] for row in result["theme_matrix"]}, {"A", "B"})

    def test_brand_feedback_excludes_small_samples(self):
        products = pd.DataFrame([
            {"product_id": "P1", "brand": "A"},
            {"product_id": "P2", "brand": "B"},
        ])
        reviews = _df(["轻便", "太重了", "容量大"], [5, 2, 5])
        reviews.loc[2, "product_id"] = "P2"
        insight = I.analyze_reviews(reviews)
        result = I.analyze_brand_feedback(products, insight["text_reviews"], min_reviews=2)

        self.assertEqual(result["eligible_brands"], 1)
        self.assertEqual(result["summary"][0]["brand"], "A")
        self.assertEqual(result["excluded_brands"], ["B"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
