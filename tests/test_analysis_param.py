"""竞品分析扩展测试：产品参数逐项对比、品牌属性对比。"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from src import analysis as A

PRODS = pd.DataFrame([
    {"product_id": "P1", "brand": "安克", "product_name": "安克A", "price": 159,
     "capacity_mah": 20000, "power_w": 22.5, "weight_g": 350, "source": "s"},
    {"product_id": "P2", "brand": "小米", "product_name": "小米B", "price": 99,
     "capacity_mah": 10000, "power_w": 18.0, "weight_g": 220, "source": "s"},
    {"product_id": "P3", "brand": "安克", "product_name": "安克C", "price": 299,
     "capacity_mah": 30000, "power_w": 65.0, "weight_g": None, "source": "s"},
])


class TestAnalysisParam(unittest.TestCase):
    def test_compare_products_all(self):
        ana = A.analyze_products(PRODS.copy(), A.DEFAULT_BANDS)
        cmp = A.compare_products(ana["df"])
        self.assertEqual(len(cmp), 3)
        self.assertEqual(list(cmp["price"]), [99, 159, 299])  # 按价格升序

    def test_compare_products_subset(self):
        ana = A.analyze_products(PRODS.copy(), A.DEFAULT_BANDS)
        cmp = A.compare_products(ana["df"], ["P1", "P2"])
        self.assertEqual(len(cmp), 2)
        self.assertSetEqual(set(cmp["product_id"]), {"P1", "P2"})

    def test_brand_attr(self):
        ana = A.analyze_products(PRODS.copy(), A.DEFAULT_BANDS)
        ba = ana["brand_attr"]
        self.assertIn("安克", ba["brand"].tolist())
        # 安克两款均价 = (159+299)/2 = 229
        ank = ba[ba["brand"] == "安克"].iloc[0]
        self.assertAlmostEqual(ank["均价"], 229.0, places=1)

    def test_weight_missing_not_fabricated(self):
        ana = A.analyze_products(PRODS.copy(), A.DEFAULT_BANDS)
        # P3 重量缺失应计入缺失统计，且不臆造
        self.assertEqual(ana["missing"]["weight_g"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
