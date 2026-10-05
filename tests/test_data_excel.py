"""数据加载测试：Excel 读取、字段识别（别名映射）、去重计数、真实 UploadedFile 上传。"""
import io
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from src import data as D

try:
    from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
    from streamlit.proto.Common_pb2 import FileURLs as FileURLsProto
    _HAVE_STREAMLIT = True
except Exception:  # pragma: no cover
    _HAVE_STREAMLIT = False

TMP = Path(__file__).resolve().parent / "_tmp_test"


def _make_uploaded_file(name: str, content: bytes) -> "UploadedFile":
    """构造一个真实的 Streamlit UploadedFile 对象（BytesIO 子类），用于贴近网页上传的测试。"""
    rec = UploadedFileRec(file_id="test-id", name=name, type="text/csv", data=content)
    urls = FileURLsProto()
    return UploadedFile(rec, urls)


class TestDataExcel(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(exist_ok=True)

    def tearDown(self):
        for f in TMP.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass

    def _sample(self):
        return pd.DataFrame([
            {"product_id": "P1", "brand": "安克", "product_name": "安克 20000mAh",
             "price": "159", "capacity_mah": "20000", "power_w": "22.5",
             "weight_g": "350", "source": "synthetic"},
            {"product_id": "P1", "brand": "安克", "product_name": "重复",
             "price": "159", "capacity_mah": "20000", "power_w": "22.5",
             "weight_g": "350", "source": "synthetic"},
        ])

    def test_load_csv(self):
        p = TMP / "p.csv"
        self._sample().to_csv(p, index=False, encoding="utf-8-sig")
        df = D.load_any(p)
        self.assertEqual(len(df), 2)

    def test_load_excel(self):
        p = TMP / "p.xlsx"
        try:
            self._sample().to_excel(p, index=False)
        except ImportError:
            self.skipTest("openpyxl 未安装，跳过 Excel 读取测试")
        df = D.load_any(p)
        self.assertEqual(len(df), 2)

    def test_alias_normalize(self):
        raw = pd.DataFrame([
            {"商品id": "P1", "品牌": "安克", "商品名": "安克 20000mAh",
             "价格": "159", "容量": "20000", "功率": "22.5",
             "重量": "350", "来源": "synthetic"},
        ])
        norm = D.normalize_columns(raw, D.PRODUCT_ALIASES)
        for col in ["product_id", "brand", "product_name", "price",
                    "capacity_mah", "power_w", "weight_g", "source"]:
            self.assertIn(col, norm.columns)

    def test_dedup_count(self):
        clean, rep = D.validate_products(self._sample())
        self.assertEqual(rep["duplicates_removed"], 1)
        self.assertEqual(rep["valid"], 1)

    @unittest.skipUnless(_HAVE_STREAMLIT, "需要 streamlit 构造真实 UploadedFile")
    def test_load_any_uploadedfile_csv(self):
        # 模拟网页端上传的 CSV（真实 UploadedFile 对象，非文件路径）
        buf = io.BytesIO()
        self._sample().to_csv(buf, index=False, encoding="utf-8-sig")
        uf = _make_uploaded_file("products.csv", buf.getvalue())
        df = D.load_any(uf)
        self.assertEqual(len(df), 2)
        self.assertIn("product_id", df.columns)

    @unittest.skipUnless(_HAVE_STREAMLIT, "需要 streamlit 构造真实 UploadedFile")
    def test_load_any_uploadedfile_xlsx(self):
        # 模拟网页端上传的 Excel（真实 UploadedFile 对象）
        buf = io.BytesIO()
        self._sample().to_excel(buf, index=False)
        uf = _make_uploaded_file("products.xlsx", buf.getvalue())
        df = D.load_any(uf)
        self.assertEqual(len(df), 2)
        self.assertIn("product_id", df.columns)

    @unittest.skipUnless(_HAVE_STREAMLIT, "需要 streamlit 构造真实 UploadedFile")
    def test_uploadedfile_full_pipeline(self):
        # 端到端：CSV 产品 + Excel 评价（混合格式上传）→ 字段识别 → 校验 → 洞察
        prod = self._sample().iloc[[0]].copy()  # 仅 P1，去重后 1 款
        prod_buf = io.BytesIO(); prod.to_csv(prod_buf, index=False, encoding="utf-8-sig")
        rev = pd.DataFrame([
            {"review_id": "R1", "product_id": "P1", "rating": 5,
             "review_text": "轻便好用", "review_date": "2025-01-01", "source": "s"},
        ])
        rev_buf = io.BytesIO(); rev.to_excel(rev_buf, index=False)
        uf_p = _make_uploaded_file("products.csv", prod_buf.getvalue())
        uf_r = _make_uploaded_file("reviews.xlsx", rev_buf.getvalue())

        prod_raw = D.normalize_columns(D.load_any(uf_p), D.PRODUCT_ALIASES)
        rev_raw = D.normalize_columns(D.load_any(uf_r), D.REVIEW_ALIASES)
        p_clean, p_rep = D.validate_products(prod_raw)
        r_clean, r_rep = D.validate_reviews(rev_raw, p_rep["valid_ids"])
        self.assertEqual(p_rep["valid"], 1)
        self.assertEqual(r_rep["valid"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
