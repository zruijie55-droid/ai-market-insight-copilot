"""网页端上传流程的逻辑级端到端验证（不依赖浏览器，使用真实 UploadedFile 对象）。

模拟 app.py 里 st.file_uploader 返回的 UploadedFile，走与网页端完全相同的
代码路径：load_any → normalize_columns（字段识别）→ validate_products /
validate_reviews（数据清洗）→ analyze_products / analyze_reviews（竞品与洞察）
→ build_hypotheses → render_markdown / render_html（报告）。

覆盖：
- 上传 CSV（产品，中文别名表头）→ 字段识别 → 去重清洗；
- 上传 XLSX（评价）→ 字段识别 → 缺失/空文本/外键不匹配清洗；
- 竞品分析、用户洞察、机会假设、报告导出内容核对。
真实浏览器截图见 tests/web_browser_test.py 的运行结果。
"""
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from src import data as D, analysis as A, insights as I, report as R

try:
    from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec
    from streamlit.proto.Common_pb2 import FileURLs as FileURLsProto
    _HAVE_ST = True
except Exception:  # pragma: no cover
    _HAVE_ST = False


def _uf(name: str, content: bytes) -> "UploadedFile":
    rec = UploadedFileRec(file_id="id", name=name, type="text/csv", data=content)
    return UploadedFile(rec, FileURLsProto())


@unittest.skipUnless(_HAVE_ST, "需要 streamlit 构造真实 UploadedFile")
class TestWebUploadFlow(unittest.TestCase):
    def _build_products_csv(self) -> bytes:
        # 中文别名表头，含一条重复 ID（P001），用于验证字段识别 + 去重清洗
        df = pd.DataFrame([
            {"商品id": "P001", "品牌": "安克", "商品名": "安克 20000mAh", "价格": 159,
             "容量": 20000, "功率": 22.5, "重量": 350, "来源": "synthetic"},
            {"商品id": "P001", "品牌": "安克", "商品名": "安克 重复", "价格": 159,
             "容量": 20000, "功率": 22.5, "重量": 350, "来源": "synthetic"},
            {"商品id": "P002", "品牌": "小米", "商品名": "小米 10000mAh", "价格": 99,
             "容量": 10000, "功率": 18, "重量": "", "来源": "synthetic"},
        ])
        buf = io.BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        return buf.getvalue()

    def _build_reviews_xlsx(self) -> bytes:
        # 英文表头；含：正常、空文本、缺失文本(NaN)、外键不匹配、评分越界
        df = pd.DataFrame([
            {"review_id": "R1", "product_id": "P001", "rating": 5,
             "review_text": "轻便好用，续航耐用", "review_date": "2025-01-01", "source": "s"},
            {"review_id": "R2", "product_id": "P001", "rating": 2,
             "review_text": "", "review_date": "2025-01-02", "source": "s"},   # 空文本
            {"review_id": "R3", "product_id": "P001", "rating": 4,
             "review_text": None, "review_date": "2025-01-03", "source": "s"},  # 缺失文本(NaN)
            {"review_id": "R4", "product_id": "P999", "rating": 3,
             "review_text": "外键不匹配", "review_date": "2025-01-04", "source": "s"},  # FK
            {"review_id": "R5", "product_id": "P001", "rating": 9,
             "review_text": "充电有点慢", "review_date": "2025-01-05", "source": "s"},  # 评分越界(保留)
        ])
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        return buf.getvalue()

    def test_full_upload_flow(self):
        # —— 1) 上传 CSV 产品（中文别名）→ 字段识别 → 校验 ——
        uf_p = _uf("products.csv", self._build_products_csv())
        prod_raw = D.normalize_columns(D.load_any(uf_p), D.PRODUCT_ALIASES)
        self.assertIn("product_id", prod_raw.columns, "中文表头未正确识别为标准列")
        p_clean, p_rep = D.validate_products(prod_raw)
        self.assertEqual(p_rep["valid"], 2, "应识别出 2 款有效产品（P001/P002）")
        self.assertEqual(p_rep["duplicates_removed"], 1, "重复 ID 应被去重")
        valid_ids = p_rep["valid_ids"]

        # —— 2) 上传 XLSX 评价 → 字段识别 → 清洗（缺失/空文本/外键）——
        uf_r = _uf("reviews.xlsx", self._build_reviews_xlsx())
        rev_raw = D.normalize_columns(D.load_any(uf_r), D.REVIEW_ALIASES)
        self.assertIn("review_text", rev_raw.columns, "英文表头未正确识别")
        r_clean, r_rep = D.validate_reviews(rev_raw, valid_ids)
        # 有效：R1（正常）、R5（评分越界但文本有效，保留并提示）
        self.assertEqual(r_rep["valid"], 2, "应保留 2 条有效评价")
        # 排除：R2 空文本、R3 缺失文本、R4 外键不匹配 = 3
        self.assertEqual(r_rep["excluded"], 3, "空文本/缺失文本/外键不匹配应被排除")
        # 缺失(NaN)评价绝不能变成 "nan" 伪文本被计入
        self.assertNotIn("nan", r_clean["review_text"].tolist())
        self.assertEqual(len(r_rep["warnings"]), 1, "评分越界应产生 1 条部分有效提示")

        # —— 3) 竞品与价格带分析 ——
        ana = A.analyze_products(p_clean)
        self.assertEqual(ana["n_products"], 2)
        self.assertIn("≤99", ana["band_counts"].index, "价格带分析应包含 ≤99 档")

        # —— 4) 用户反馈洞察（含缺失文本清洗后的文本洞察）——
        ins = I.analyze_reviews(r_clean)
        self.assertEqual(ins["n_text"], 2, "文本洞察应仅基于 2 条有效文本")
        self.assertIn("便携/重量", set(ins["text_reviews"].iloc[0]["themes"]))

        # —— 5) 产品机会假设 ——
        merged = A.merge_review_rating(p_clean, r_clean)
        hypos = I.build_hypotheses(merged, ins["text_reviews"], ana["band_order"])
        self.assertIsInstance(hypos, list)
        self.assertTrue(len(hypos) >= 1)

        # —— 6) 报告导出内容核对 ——
        ctx = {
            "gen_time": "2025-09-21 00:00", "source_marker": "synthetic",
            "product_report": p_rep, "review_report": r_rep,
            "prod": ana, "insight": ins, "hypos": hypos,
            "use_llm": False, "band_order": ana["band_order"],
        }
        md = R.render_markdown(ctx)
        html = R.render_html(ctx)
        self.assertIn("待验证", md, "报告应标注机会为待验证")
        self.assertIn("情感分布", md, "报告应含情感分布章节")
        self.assertIn("数据质量", md, "报告应含数据质量章节")
        self.assertIn("数据质量", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
