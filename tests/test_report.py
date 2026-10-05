"""报告 HTML 渲染测试：结构化列表、表格和行内强调。"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import report as R


class TestReportHtml(unittest.TestCase):
    def _ctx(self):
        return {
            "gen_time": "2026-10-02 10:00",
            "product_report": {"total": 1, "valid": 1, "excluded": 0},
            "review_report": {"total": 1, "valid": 1, "excluded": 0},
            "prod": {"n_products": 1, "n_brands": 1, "price_median": 99},
            "insight": {
                "n_text": 1, "n_rated": 1, "unmatched": 0,
                "sentiment_summary": {"positive": 1, "negative": 0, "neutral": 0},
                "theme_stats": [], "theme_sentiment": [], "pain_points": [],
            },
            "hypos": [],
        }

    def test_bold_markdown_is_rendered(self):
        html = R.render_html(self._ctx())
        self.assertIn("<strong>1</strong>", html)
        self.assertNotIn("**1**", html)

    def test_list_items_are_wrapped(self):
        html = R.render_html(self._ctx())
        self.assertIn("<ul><li>", html)
        self.assertIn("</li></ul>", html)

    def test_content_is_html_escaped(self):
        ctx = self._ctx()
        ctx["source_marker"] = "<script>alert(1)</script>"
        html = R.render_html(ctx)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_report_uses_supplied_source_and_mode(self):
        ctx = self._ctx()
        ctx["source_marker"] = "产品：products.xlsx；评价：reviews.csv"
        ctx["use_llm"] = True
        html = R.render_html(ctx)
        self.assertIn("products.xlsx", html)
        self.assertIn("用户反馈主题频次（大模型增强版）", html)

    def test_report_body_precedes_chart_appendix(self):
        html = R.render_html(self._ctx(), {"band": "<div id='test-chart'></div>"})
        self.assertLess(html.index("<h1>"), html.index("附录：图表"))
        self.assertLess(html.index("附录：图表"), html.index("test-chart"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
