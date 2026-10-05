"""报告生成（对应 PRD F4）。

提供两种下载格式：
- Markdown（主交付，纯文本，可直接存档/二次编辑）
- HTML（含嵌入的 Plotly 图表 div，需在浏览器查看）

报告中明确标注数据来源（synthetic）、数据质量、分析口径与限制，
所有机会均为「待验证假设」，不给出市场结论或销量预测。
"""
from __future__ import annotations

from datetime import datetime
import html as _html
import re


def _md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def render_markdown(ctx: dict) -> str:
    gen = ctx.get("gen_time") or datetime.now().strftime("%Y-%m-%d %H:%M")
    src = ctx.get("source_marker", "synthetic（模拟数据，不代表真实市场）")
    pr = ctx.get("product_report", {})
    rr = ctx.get("review_report", {})
    prod = ctx.get("prod", {})
    ins = ctx.get("insight", {})
    hypos = ctx.get("hypos", [])
    use_llm = ctx.get("use_llm", False)
    mode = "大模型增强版" if use_llm else "规则版"

    out = []
    out.append("# AI 市场洞察与产品机会发现平台 · 分析报告")
    out.append("")
    out.append(f"> 生成时间：{gen}　|　数据来源：{src}")
    out.append(f"> 本报告由 **{mode}** 分析自动生成，所有结论均为**待验证假设**，"
               "不代表真实市场份额、销量或商业判断。")
    out.append("")

    # 1. 数据质量
    out.append("## 一、数据质量")
    out.append("")
    out.append(f"- 产品表：总 {pr.get('total','-')} 行，有效 {pr.get('valid','-')} 行，"
               f"排除 {pr.get('excluded','-')} 行")
    out.append(f"- 评价表：总 {rr.get('total','-')} 行，有效 {rr.get('valid','-')} 行，"
               f"排除 {rr.get('excluded','-')} 行")
    if pr.get("issues"):
        out.append("")
        out.append("**产品表排除明细：**")
        out.append(_md_table(["行号", "原因"],
                             [[i["row"], i["reason"]] for i in pr["issues"]]))
    if rr.get("issues"):
        out.append("")
        out.append("**评价表排除明细：**")
        out.append(_md_table(["行号", "原因"],
                             [[i["row"], i["reason"]] for i in rr["issues"]]))
    if rr.get("warnings"):
        out.append("")
        out.append("**部分有效提示（行保留但相应分组剔除）：**")
        for w in rr["warnings"][:30]:
            out.append(f"- {w}")
    out.append("")

    # 2. 关键指标
    out.append("## 二、关键指标（竞品与价格带）")
    out.append("")
    out.append(f"- 产品数：**{prod.get('n_products','-')}**　品牌数：**{prod.get('n_brands','-')}**　"
               f"价格中位数：**{prod.get('price_median','-')} 元**")
    miss = prod.get("missing", {})
    if miss:
        out.append(f"- 参数缺失：重量 {miss.get('weight_g',0)} 条、"
                   f"容量 {miss.get('capacity_mah',0)} 条、功率 {miss.get('power_w',0)} 条")
    out.append("")
    bc = prod.get("band_counts")
    if bc is not None:
        out.append("**价格带分布：**")
        out.append(_md_table(["价格带(元)", "产品数"],
                             [[k, int(v)] for k, v in bc.items()]))
    out.append("")
    bs = prod.get("band_stats")
    if bs is not None and len(bs) > 0:
        out.append("**各价格带参数：**")
        rows = []
        for idx, row in bs.iterrows():
            # 某些价格带可能没有产品（用户上传数据常见）：缺失项显示为「-」，避免 int(NaN) 崩溃
            n = int(row["产品数"]) if pd_notna(row["产品数"]) else 0
            avg = round(row["均价"], 1) if pd_notna(row["均价"]) else "-"
            cap = int(row["容量中位"]) if pd_notna(row["容量中位"]) else "-"
            pwr = round(row["功率中位"], 1) if pd_notna(row["功率中位"]) else "-"
            wmiss = int(row["重量缺失"]) if pd_notna(row["重量缺失"]) else 0
            rows.append([idx, n, avg, cap, pwr, wmiss])
        out.append(_md_table(["价格带", "产品数", "均价", "容量中位(mAh)", "功率中位(W)", "重量缺失"],
                             rows))
    out.append("")

    # 3. 主题频次
    out.append(f"## 三、用户反馈主题频次（{mode}）")
    out.append("")
    out.append(f"- 参与文本洞察的有效评价：**{ins.get('n_text','-')}** 条　"
               f"其中有效评分：**{ins.get('n_rated','-')}** 条　"
               f"未命中任何主题：**{ins.get('unmatched','-')}** 条")
    out.append("- 说明：正向 / 负向 / 负向率来自情感标注；低分 / 高分仅按评分分组"
               "（1–2 低分 / 4–5 高分）；一条评价可命中多主题，故各主题占比之和可超过 100%。")
    out.append("")
    ts = ins.get("theme_stats", [])
    if ts:
        out.append(_md_table(
            ["主题", "提及数", "占有效评价%", "正向", "负向", "负向率%", "低分(1-2)", "高分(4-5)"],
            [[t["theme"], t["mentions"], t["pct"], t["pos"], t["neg"], t["neg_rate"],
              t["low"], t["high"]] for t in ts]))
    out.append("")

    # 3.1 情感分布与痛点
    out.append("### 3.1 情感分布与投诉热点")
    out.append("")
    ss_sum = ins.get("sentiment_summary", {})
    sentiment_method = "大模型增强标注（超出调用上限部分回退词典）" if use_llm else "中文情感词典标注"
    out.append(f"- 情感分布（{sentiment_method}）：正向 **{ss_sum.get('positive', 0)}** 条、"
               f"负向 **{ss_sum.get('negative', 0)}** 条、中性 **{ss_sum.get('neutral', 0)}** 条")
    out.append("- 主题 × 情感矩阵（行=主题，列=情感计数；负向越高越需关注）：")
    ts_mat = ins.get("theme_sentiment", [])
    if ts_mat:
        out.append(_md_table(
            ["主题", "正向", "负向", "中性"],
            [[m["theme"], m["positive"], m["negative"], m["neutral"]] for m in ts_mat]))
    out.append("")
    pains = ins.get("pain_points", [])
    if pains:
        out.append("**痛点排序（按负向率，样本≥8）：**")
        for p in pains:
            out.append(f"- {p['theme']}：提及 {p['mentions']} 次，其中负向 {p['neg']} 次"
                       f"（负向率 {p['neg_rate']}%）")
    else:
        out.append("- 未检出足够样本量的显著痛点（各主题负向样本均 < 8 条）。")
    out.append("")
    out.append("> 说明：情感为词典规则标注（LLM 启用时为增强标注），存在误判，"
               "仅用于快速定位反馈集中的方向，不作为结论。")
    out.append("")

    # 3.2 品牌反馈
    out.append("### 3.2 品牌用户反馈对比")
    out.append("")
    brand_feedback = ins.get("brand_feedback", {})
    brand_summary = brand_feedback.get("summary", [])
    if brand_summary:
        out.append(f"- 仅展示有效评价不少于 **{brand_feedback.get('min_reviews', 3)}** 条的品牌；"
                   "负向率分母为该品牌全部有效文本评价。")
        out.append(_md_table(
            ["品牌", "评价数", "有效评分数", "负向数", "负向率%", "平均评分", "首要负向主题"],
            [[b["brand"], b["reviews"], b["rated"], b["negative"], b["neg_rate"],
              b["avg_rating"] if b["avg_rating"] is not None else "-",
              b["top_negative_theme"]] for b in brand_summary]))
        excluded = brand_feedback.get("excluded_brands", [])
        if excluded:
            out.append("")
            out.append("- 样本不足、未参与品牌排序：" + "、".join(excluded))
    else:
        out.append("- 暂无达到最小评价样本量的品牌，未进行品牌负向率排序。")
    out.append("")

    # 3.3 时间趋势
    out.append("### 3.3 评价时间趋势")
    out.append("")
    time_summary = ins.get("time_summary", {})
    monthly_trend = ins.get("monthly_trend", [])
    if monthly_trend:
        out.append(f"- 有效日期：**{time_summary.get('n_dated', 0)}** 条，覆盖 "
                   f"**{time_summary.get('date_start', '-')} 至 "
                   f"{time_summary.get('date_end', '-')}**，共 "
                   f"**{time_summary.get('n_months', 0)}** 个月。")
        out.append(_md_table(
            ["月份", "评价量", "正向", "负向", "中性", "负向率%", "平均评分"],
            [[m["month"], m["reviews"], m["positive"], m["negative"], m["neutral"],
              m["neg_rate"], m["avg_rating"] if m["avg_rating"] is not None else "-"]
             for m in monthly_trend]))
        out.append("")
        out.append("> 时间趋势为描述性统计；月份样本量不同，负向率波动不代表因果或市场变化。")
    else:
        out.append("- 没有可用于时间趋势的有效评价日期。")
    out.append("")

    # 4. 机会假设
    out.append("## 四、产品机会假设（待验证）")
    out.append("")
    if not hypos:
        out.append("- 未生成假设。")
    for i, h in enumerate(hypos, 1):
        ev = "、".join(h.get("evidence_ids", []) or []) or "—"
        out.append(f"### 假设 {i}：{h.get('title','')}")
        out.append("")
        out.append(h.get("detail", ""))
        out.append("")
        out.append(f"- 范围：{h.get('scope','-')}　样本量：{h.get('sample_size','-')}")
        out.append(f"- 可信度说明：{h.get('confidence','-')}")
        out.append(f"- 证据评价 ID：{ev}")
        out.append("")

    # 5. 限制
    out.append("## 五、限制与说明")
    out.append("")
    out.append("- 数据均为模拟生成（source=synthetic），**不代表真实市场**；")
    if use_llm:
        used = ins.get("llm_used")
        budget = ins.get("llm_budget")
        cap = f"（情感标注实际调用模型 {used}/{budget} 条，超出部分自动回退规则版，以控制费用）" \
            if used is not None else ""
        out.append("- 本次启用了**大模型增强**（API Key 经环境变量配置）：情感/主题/假设描述由模型辅助生成，"
                   f"仍属**待验证**内容，可能含模型偏差，需人工复核；{cap}")
    else:
        out.append("- 本次未启用大模型，主题与情感识别为**透明关键词 / 情感词典规则**，存在误判与漏判，"
                   "未命中主题的评价已在上文统计；")
    out.append("- 不臆造销量、市场份额或销售额；机会仅作**假设**，需结合人工研判与进一步验证；")
    out.append("- 大模型 API 为可选能力，需用户显式配置密钥后启用；未配置时全部基础功能（数据清洗/"
               "竞品分析/规则洞察）照常运行。")
    out.append("")
    out.append("---")
    out.append("*由 AI Market Insight Copilot（V1.2.0 规则版）生成 · 仅供学习演示*")
    return "\n".join(out)


def render_html(ctx: dict, figs: dict = None) -> str:
    """生成带样式的 HTML 报告；figs 为 {name: plotly_div_html}。"""
    figs = figs or {}
    md = render_markdown(ctx)
    body_parts = []
    in_table = False
    in_list = False
    table_rows = []

    def close_table():
        nonlocal in_table, table_rows
        if in_table:
            body_parts.append(_render_table(table_rows))
            in_table = False
            table_rows = []

    def close_list():
        nonlocal in_list
        if in_list:
            body_parts.append("</ul>")
            in_list = False

    for line in md.split("\n"):
        is_table_line = line.startswith("|") and "|" in line[1:]
        if in_table and not is_table_line:
            close_table()
        if in_list and not line.startswith("- "):
            close_list()

        if line.startswith("### "):
            body_parts.append(f"<h3>{_render_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            body_parts.append(f"<h2>{_render_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            body_parts.append(f"<h1>{_render_inline(line[2:])}</h1>")
        elif line.startswith("> "):
            body_parts.append(f"<blockquote>{_render_inline(line[2:])}</blockquote>")
        elif is_table_line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue
            if not in_table:
                in_table = True
                table_rows = []
            table_rows.append(cells)
        elif line.strip() == "":
            continue
        elif line.startswith("- "):
            if not in_list:
                body_parts.append("<ul>")
                in_list = True
            body_parts.append(f"<li>{_render_inline(line[2:])}</li>")
        elif line == "---":
            body_parts.append("<hr>")
        else:
            body_parts.append(f"<p>{_render_inline(line)}</p>")
    close_table()
    close_list()

    figs_html = ""
    if figs:
        figs_html = ("<section class='charts'><h2>附录：图表</h2>" +
                     "\n".join(figs.values()) + "</section>")
    css = """
    <style>
      body{font-family:-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
           max-width:960px;margin:24px auto;padding:0 20px;color:#1f2328;line-height:1.7;}
      h1{color:#c1121f;border-bottom:3px solid #c1121f;padding-bottom:8px;}
      h2{color:#c1121f;margin-top:32px;border-left:5px solid #c1121f;padding-left:10px;}
      h3{color:#333;margin-top:20px;}
      blockquote{background:#fff8e6;border-left:4px solid #f0a500;margin:12px 0;padding:8px 14px;color:#6b4e00;}
      table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px;}
      th,td{border:1px solid #ddd;padding:7px 10px;text-align:left;}
      th{background:#f5f5f5;}
      tr:nth-child(even){background:#fafafa;}
      li{margin:4px 0;}
      .charts{margin-top:36px;border-top:1px solid #ddd;padding-top:8px;}
    </style>"""
    return f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>AI 市场洞察报告</title>{css}</head><body>{''.join(body_parts)}{figs_html}</body></html>"


def _render_table(rows: list[list]) -> str:
    if not rows:
        return ""
    head, *body = rows
    th = "".join(f"<th>{_render_inline(c)}</th>" for c in head)
    trs = "".join(
        "<tr>" + "".join(f"<td>{_render_inline(c)}</td>" for c in r) + "</tr>"
        for r in body
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def _render_inline(value) -> str:
    """渲染报告内有限的 Markdown 行内语法，同时保持 HTML 转义。"""
    escaped = _html.escape(str(value))
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def pd_notna(x):
    try:
        import pandas as pd
        return pd.notna(x)
    except Exception:
        return x is not None
