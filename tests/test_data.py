"""F1 数据校验测试：字段缺失、重复 ID、无效数值、外键不匹配、空评价、评分越界、正常/空数据。"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from src import data as D


def prod_row(**kw):
    base = {"product_id": "P1", "brand": "A", "product_name": "x", "price": 100,
            "capacity_mah": 1000, "power_w": 10, "weight_g": 200, "source": "s"}
    base.update(kw)
    return base


class TestProductValidation(unittest.TestCase):
    def test_missing_column(self):
        df = pd.DataFrame([{"product_id": "P1", "brand": "A", "product_name": "x",
                            "capacity_mah": 1000, "power_w": 10, "source": "s"}])
        _, rep = D.validate_products(df)
        self.assertEqual(rep["valid"], 0)
        self.assertTrue(any("缺少必填列" in i["reason"] for i in rep["issues"]))

    def test_duplicate_id(self):
        df = pd.DataFrame([prod_row(), prod_row(product_name="y")])
        _, rep = D.validate_products(df)
        self.assertEqual(rep["valid"], 1)
        self.assertEqual(rep["excluded"], 1)

    def test_negative_price(self):
        _, rep = D.validate_products(pd.DataFrame([prod_row(price=-5)]))
        self.assertEqual(rep["valid"], 0)

    def test_invalid_capacity(self):
        _, rep = D.validate_products(pd.DataFrame([prod_row(capacity_mah=-100)]))
        self.assertEqual(rep["valid"], 0)
        _, rep2 = D.validate_products(pd.DataFrame([prod_row(capacity_mah=10.5)]))
        self.assertEqual(rep2["valid"], 0, "非整数容量必须被排除")

    def test_invalid_power(self):
        _, rep = D.validate_products(pd.DataFrame([prod_row(power_w=0)]))
        self.assertEqual(rep["valid"], 0)

    def test_valid_sample(self):
        df = pd.DataFrame([
            prod_row(product_id="P1", weight_g=200),
            prod_row(product_id="P2", weight_g=""),
        ])
        clean, rep = D.validate_products(df)
        self.assertEqual(rep["valid"], 2)
        self.assertEqual(rep["valid_ids"], {"P1", "P2"})
        self.assertTrue(pd.isna(clean.iloc[1]["weight_g"]))

    def test_empty_df(self):
        clean, rep = D.validate_products(pd.DataFrame())
        self.assertEqual(rep["valid"], 0)
        self.assertEqual(rep["total"], 0)


class TestReviewValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prod_clean, cls.prod_rep = D.validate_products(pd.DataFrame([
            prod_row(product_id="P1"), prod_row(product_id="P2")]))

    def _rev(self, **kw):
        base = {"review_id": "R1", "product_id": "P1", "rating": 5,
                "review_text": "好", "review_date": "2025-01-01", "source": "s"}
        base.update(kw)
        return pd.DataFrame([base])

    def test_fk_mismatch(self):
        clean, rep = D.validate_reviews(self._rev(product_id="PX"), self.prod_rep["valid_ids"])
        self.assertEqual(rep["valid"], 0)

    def test_empty_text(self):
        clean, rep = D.validate_reviews(self._rev(review_text=""), self.prod_rep["valid_ids"])
        self.assertEqual(rep["valid"], 0)

    def test_missing_text_nan_excluded(self):
        # 缺失评价（NaN/None）不应被 astype(str) 变成字面量 "nan" 而误判为有效文本
        import numpy as np
        df = pd.DataFrame([{
            "review_id": "R1", "product_id": "P1", "rating": 5,
            "review_text": np.nan, "review_date": "2025-01-01", "source": "s"}])
        clean, rep = D.validate_reviews(df, self.prod_rep["valid_ids"])
        self.assertEqual(rep["valid"], 0, "缺失评价文本必须按空文本排除，不得计入有效样本")
        # 验证清洗后不会留下 "nan" 这种伪文本
        self.assertNotIn("nan", clean["review_text"].tolist() if len(clean) else [])

    def test_missing_text_none_excluded(self):
        df = pd.DataFrame([{
            "review_id": "R1", "product_id": "P1", "rating": 5,
            "review_text": None, "review_date": "2025-01-01", "source": "s"}])
        clean, rep = D.validate_reviews(df, self.prod_rep["valid_ids"])
        self.assertEqual(rep["valid"], 0)

    def test_whitespace_text_excluded(self):
        # 纯空格评价应被当空文本排除
        clean, rep = D.validate_reviews(self._rev(review_text="   \t  "),
                                       self.prod_rep["valid_ids"])
        self.assertEqual(rep["valid"], 0)

    def test_duplicate_review_id(self):
        df = pd.DataFrame([
            {"review_id": "R1", "product_id": "P1", "rating": 5, "review_text": "好",
             "review_date": "2025-01-01", "source": "s"},
            {"review_id": "R1", "product_id": "P2", "rating": 4, "review_text": "不错",
             "review_date": "2025-01-02", "source": "s"}])
        _, rep = D.validate_reviews(df, self.prod_rep["valid_ids"])
        self.assertEqual(rep["valid"], 1)
        self.assertEqual(rep["excluded"], 1)

    def test_invalid_rating_kept_with_warning(self):
        _, rep = D.validate_reviews(self._rev(rating=9), self.prod_rep["valid_ids"])
        self.assertEqual(rep["valid"], 1)
        self.assertTrue(any("评分" in w for w in rep["warnings"]))

    def test_missing_rating_and_date_kept(self):
        _, rep = D.validate_reviews(self._rev(rating="", review_date=""),
                                    self.prod_rep["valid_ids"])
        self.assertEqual(rep["valid"], 1)
        self.assertTrue(any("评分" in w for w in rep["warnings"]))
        self.assertTrue(any("日期" in w for w in rep["warnings"]))

    def test_normal(self):
        df = pd.DataFrame([
            {"review_id": "R1", "product_id": "P1", "rating": 5, "review_text": "轻便好用",
             "review_date": "2025-01-01", "source": "s"},
            {"review_id": "R2", "product_id": "P2", "rating": 2, "review_text": "太重了",
             "review_date": "2025-02-01", "source": "s"}])
        _, rep = D.validate_reviews(df, self.prod_rep["valid_ids"])
        self.assertEqual(rep["valid"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
