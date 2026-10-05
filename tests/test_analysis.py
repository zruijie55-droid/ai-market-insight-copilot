"""F2 竞品与价格带分析测试：基本指标、价格带、缺失、空数据、评价关联。"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from src import analysis as A

BANDS = A.DEFAULT_BANDS
ORDER = [b[2] for b in BANDS]


class TestAnalysis(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame([
            {"product_id": "P1", "brand": "A", "product_name": "x", "price": 80,
             "capacity_mah": 5000, "power_w": 18, "weight_g": 200, "source": "s"},
            {"product_id": "P2", "brand": "B", "product_name": "y", "price": 150,
             "capacity_mah": 10000, "power_w": 22, "weight_g": 300, "source": "s"},
            {"product_id": "P3", "brand": "A", "product_name": "z", "price": 250,
             "capacity_mah": 20000, "power_w": 45, "weight_g": 400, "source": "s"},
            {"product_id": "P4", "brand": "C", "product_name": "w", "price": 350,
             "capacity_mah": 30000, "power_w": 100, "weight_g": None, "source": "s"},
        ])

    def test_basic(self):
        r = A.analyze_products(self.df)
        self.assertEqual(r["n_products"], 4)
        self.assertEqual(r["n_brands"], 3)
        # 价格 [80,150,250,350] 中位数 = (150+250)/2 = 200
        self.assertAlmostEqual(r["price_median"], 200)

    def test_band_counts(self):
        r = A.analyze_products(self.df)
        bc = r["band_counts"]
        self.assertEqual(bc[ORDER[0]], 1)
        self.assertEqual(bc[ORDER[1]], 1)
        self.assertEqual(bc[ORDER[2]], 1)
        self.assertEqual(bc[ORDER[3]], 1)

    def test_missing(self):
        r = A.analyze_products(self.df)
        self.assertEqual(r["missing"]["weight_g"], 1)
        self.assertEqual(r["missing"]["capacity_mah"], 0)

    def test_empty(self):
        empty = pd.DataFrame(columns=["product_id", "brand", "product_name", "price",
                                      "capacity_mah", "power_w", "weight_g", "source"])
        r = A.analyze_products(empty)
        self.assertEqual(r["n_products"], 0)

    def test_merge_review_rating(self):
        rev = pd.DataFrame([
            {"review_id": "R1", "product_id": "P1", "rating": 5, "review_text": "轻便",
             "review_date": "2025-01-01", "source": "s", "rating_valid": True,
             "date_valid": True, "text_valid": True},
            {"review_id": "R2", "product_id": "P4", "rating": 2, "review_text": "重",
             "review_date": "2025-01-01", "source": "s", "rating_valid": True,
             "date_valid": True, "text_valid": True}])
        m = A.merge_review_rating(self.df, rev)
        self.assertEqual(len(m), 2)
        self.assertIn("price_band", m.columns)

    def test_build_price_bands(self):
        bands = A.build_price_bands(99, 199, 299)
        self.assertEqual([b[2] for b in bands], ["≤99", "100–199", "200–299", "≥300"])
        self.assertEqual(A.price_band_label(200, bands), "200–299")

    def test_build_price_bands_rejects_invalid_edges(self):
        for edges in [(199, 99, 299), (99, 99, 299), (-1, 199, 299)]:
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                A.build_price_bands(*edges)


if __name__ == "__main__":
    unittest.main(verbosity=2)
