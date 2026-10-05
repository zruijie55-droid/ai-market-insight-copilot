"""端到端非交互验证：内置模拟数据 → 校验 → 分析 → 洞察 → 假设 → 报告。

不依赖 Streamlit / 大模型，验证整条数据管线在能执行的环境中真实跑通。
运行：python tests/pipeline_smoke.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from src import data as D, analysis as A, insights as I, report as R

print("=== 端到端管线验证（内置模拟数据）===")
prod_raw = D.load_builtin("products")
rev_raw = D.load_builtin("reviews")
print(f"原始：产品 {len(prod_raw)} 行，评价 {len(rev_raw)} 行")

prod_clean, prod_rep = D.validate_products(prod_raw)
rev_clean, rev_rep = D.validate_reviews(rev_raw, prod_rep["valid_ids"])
print(f"[F1] 产品表 有效 {prod_rep['valid']} / 排除 {prod_rep['excluded']}；"
      f"评价表 有效 {rev_rep['valid']} / 排除 {rev_rep['excluded']}；"
      f"提示 {len(rev_rep['warnings'])} 条")
assert prod_rep["excluded"] == 0, "内置模拟产品应全部有效"
# 评价表中仅"空文本"1 条被整行排除；缺失评分/日期的 2 条保留并提示（符合 PRD）
assert rev_rep["excluded"] == 1, f"内置模拟评价应排除 1 条空文本，实际 {rev_rep['excluded']}"
assert len(rev_rep["warnings"]) == 2, f"应提示 2 条部分有效，实际 {len(rev_rep['warnings'])}"

ana = A.analyze_products(prod_clean)
print(f"[F2] 产品数 {ana['n_products']}，品牌数 {ana['n_brands']}，"
      f"价格中位数 {ana['price_median']} 元")
print("     价格带分布：", dict(ana["band_counts"]))

ins = I.analyze_reviews(rev_clean)
ins["brand_feedback"] = I.analyze_brand_feedback(prod_clean, ins["text_reviews"])
print(f"[F3] 文本洞察样本 {ins['n_text']} 条，有效评分 {ins['n_rated']} 条，"
      f"未命中主题 {ins['unmatched']} 条")
print(f"     情感分布：{ins['sentiment_summary']}")
assert ins["monthly_trend"], "应生成月度评价趋势"
print(f"     时间范围：{ins['time_summary']['date_start']} 至 "
      f"{ins['time_summary']['date_end']}，{ins['time_summary']['n_months']} 个月")
top = max(ins["theme_stats"], key=lambda t: t["mentions"])
print(f"     最高频主题：{top['theme']}（{top['mentions']} 次，{top['pct']}%）")
pains = ins.get("pain_points", [])
print(f"     痛点（按负向率，样本≥8）："
      f"{[p['theme'] + '(' + str(p['neg_rate']) + '%)' for p in pains] or '无'}")
assert ins["brand_feedback"]["summary"], "应生成达到样本门槛的品牌反馈对比"
print(f"     品牌反馈：{ins['brand_feedback']['eligible_brands']} 个品牌达到 "
      f"≥{ins['brand_feedback']['min_reviews']} 条评价门槛")

merged = A.merge_review_rating(prod_clean, rev_clean)
hypos = I.build_hypotheses(merged, ins["text_reviews"], ana["band_order"])
print(f"[F4] 生成机会假设 {len(hypos)} 条")
for i, h in enumerate(hypos[:3], 1):
    print(f"     假设{i}：{h['title']}（范围 {h['scope']}，样本 {h['sample_size']}）")

ctx = {
    "gen_time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    "source_marker": "synthetic（模拟数据，不代表真实市场）",
    "product_report": prod_rep, "review_report": rev_rep,
    "prod": ana, "insight": ins, "hypos": hypos,
    "use_llm": False, "band_order": ana["band_order"],
}
md = R.render_markdown(ctx)
html = R.render_html(ctx)
out_md = ROOT / "output" / "demo_report.md"
out_html = ROOT / "output" / "demo_report.html"
out_md.parent.mkdir(parents=True, exist_ok=True)
out_md.write_text(md, encoding="utf-8-sig")
out_html.write_text(html, encoding="utf-8-sig")
# 断言报告包含关键章节与情感信息，确保渲染真实可用
assert "情感分布" in md, "报告应含情感分布章节"
assert "评价时间趋势" in md, "报告应含评价时间趋势章节"
assert "品牌用户反馈对比" in md, "报告应含品牌用户反馈章节"
assert "待验证" in md, "报告应标注机会为待验证"
print(f"\n报告已生成：\n  {out_md} ({out_md.stat().st_size} bytes)\n  "
      f"{out_html} ({out_html.stat().st_size} bytes)")
print("\n=== 端到端验证通过 ===")
