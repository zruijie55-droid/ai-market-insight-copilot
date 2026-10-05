"""AI 市场洞察与产品机会发现平台 · V1.2.0（规则版 + 可选大模型增强）。

页面结构（左侧导航）：
  0 项目简介
  1 数据上传与质量 (模块1)
  2 竞品与价格带分析 (模块2)
  3 用户反馈洞察 (模块3)
  4 产品机会假设与导出 (模块4/5)

特性：
- 支持 CSV / Excel(.xlsx) 上传，自动字段识别（常见中文/英文表头别名映射）；
- 无 API Key 时全部基础功能（数据清洗/竞品分析/规则洞察）照常运行；
- 配置 OPENAI_API_KEY 等环境变量并勾选「启用大模型增强」后，情感/主题/假设描述可由
  大模型辅助生成（仍标注为待验证，绝不表述为已证实结论）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import data as D, analysis as A, insights as I, report as R, llm as LLM  # noqa: E402

st.set_page_config(page_title="AI 市场洞察 Copilot (V1.2.0)", layout="wide",
                   initial_sidebar_state="expanded")

# ----------------------------------------------------------------------------
# 会话状态初始化
# ----------------------------------------------------------------------------
ss = st.session_state
if "data_version" not in ss:
    ss.products_raw = D.load_builtin("products")
    ss.reviews_raw = D.load_builtin("reviews")
    ss.source_label = "仓库自带模拟数据（synthetic）"
    ss.product_source = "内置 products.csv"
    ss.review_source = "内置 reviews.csv"
    ss.data_version = 1
if "computed_key" not in ss:
    ss.computed_key = None
if "product_source" not in ss:
    ss.product_source = "内置 products.csv"
if "review_source" not in ss:
    ss.review_source = "内置 reviews.csv"

llm_available = LLM.is_available()


# ----------------------------------------------------------------------------
# 侧边栏：数据来源 + 价格带配置 + 大模型开关 + 导航
# ----------------------------------------------------------------------------
st.sidebar.title("AI 市场洞察 Copilot")
st.sidebar.caption("V1.2.0 · 本地规则版 · 大模型可选")

source_status = st.sidebar.container()

up_p = st.sidebar.file_uploader("上传产品表 (CSV/Excel)", type=["csv", "xlsx"], key="up_p")
up_r = st.sidebar.file_uploader("上传评价表 (CSV/Excel)", type=["csv", "xlsx"], key="up_r")


def apply_upload(uploaded, kind: str, aliases: dict) -> None:
    """读取上传文件；失败时保留上一份可用数据并在侧栏显示原因。"""
    if uploaded is None:
        return
    signature = (getattr(uploaded, "file_id", None), uploaded.name, uploaded.size)
    signature_key = f"{kind}_upload_signature"
    error_key = f"{kind}_upload_error"
    if ss.get(signature_key) != signature:
        try:
            raw = D.normalize_columns(D.load_any(uploaded), aliases)
        except Exception as exc:
            ss[error_key] = f"{uploaded.name} 读取失败：{exc}"
        else:
            if kind == "product":
                ss.products_raw = raw
                ss.product_source = uploaded.name
            else:
                ss.reviews_raw = raw
                ss.review_source = uploaded.name
            ss.source_label = f"用户上传：{ss.product_source} + {ss.review_source}"
            ss.data_version += 1
            ss[error_key] = None
        ss[signature_key] = signature
    if ss.get(error_key):
        st.sidebar.error(ss[error_key])


apply_upload(up_p, "product", D.PRODUCT_ALIASES)
apply_upload(up_r, "review", D.REVIEW_ALIASES)
if st.sidebar.button("↺ 加载示例模拟数据"):
    ss.products_raw = D.load_builtin("products")
    ss.reviews_raw = D.load_builtin("reviews")
    ss.source_label = "仓库自带模拟数据（synthetic）"
    ss.product_source = "内置 products.csv"
    ss.review_source = "内置 reviews.csv"
    ss.data_version += 1
    ss.product_upload_error = ss.review_upload_error = None

with source_status:
    st.markdown("**当前数据**")
    st.caption(f"产品：{ss.product_source}\n\n评价：{ss.review_source}")

st.sidebar.markdown("---")
st.sidebar.markdown("**价格带边界（元）**")
e1 = st.sidebar.number_input("≤ 第一档上限", value=99, step=10, key="e1")
e2 = st.sidebar.number_input("第二档上限", value=199, step=10, key="e2")
e3 = st.sidebar.number_input("第三档上限", value=299, step=10, key="e3")
try:
    bands = A.build_price_bands(e1, e2, e3)
except ValueError as exc:
    st.sidebar.error(str(exc))
    st.error("价格带配置无效，请在侧栏修正后继续分析。")
    st.stop()
band_order = [b[2] for b in bands]

st.sidebar.markdown("---")
st.sidebar.markdown("**大模型增强（可选）**")
if llm_available:
    st.sidebar.success("✅ 检测到 API Key 环境变量")
    use_llm = st.sidebar.checkbox("启用大模型增强", value=False,
                                  help="情感/主题/假设描述由模型辅助生成，仍标注为待验证")
else:
    st.sidebar.info("未配置 API Key：使用规则版（无需大模型）。")
    use_llm = False

page = st.sidebar.radio("导航", [
    "0 项目简介", "1 数据上传与质量 (模块1)", "2 竞品与价格带分析 (模块2)",
    "3 用户反馈洞察 (模块3)", "4 机会假设与导出 (模块4/5)",
])

# ----------------------------------------------------------------------------
# 校验 + 分析（仅在数据/配置/模式变化时重算）
# ----------------------------------------------------------------------------
computed_key = (ss.data_version, e1, e2, e3, use_llm)
if ss.computed_key != computed_key:
    prod_clean, prod_rep = D.validate_products(ss.products_raw)
    if prod_rep["valid_ids"]:
        rev_clean, rev_rep = D.validate_reviews(ss.reviews_raw, prod_rep["valid_ids"])
    else:
        rev_clean, rev_rep = (ss.reviews_raw.iloc[0:0],
                              {"total": 0, "valid": 0, "excluded": 0,
                               "duplicates_removed": 0,
                               "issues": [{"row": "-", "field": "-",
                                           "reason": "产品表无有效行，评价表无法校验外键"}],
                               "warnings": []})
    ss.prod_clean, ss.prod_rep = prod_clean, prod_rep
    ss.rev_clean, ss.rev_rep = rev_clean, rev_rep
    ss.analysis = A.analyze_products(prod_clean, bands) if len(prod_clean) else None
    ss.insight = I.analyze_reviews(rev_clean, use_llm=use_llm) if len(rev_clean) else None
    ss.use_llm = use_llm
    if ss.analysis and ss.insight:
        ss.insight["brand_feedback"] = I.analyze_brand_feedback(
            prod_clean, ss.insight["text_reviews"]
        )
        merged = A.merge_review_rating(prod_clean, rev_clean, bands)
        ctx_summary = (f"共 {ss.analysis['n_products']} 款产品、"
                       f"{ss.insight['n_text']} 条有效评价，价格中位数 "
                       f"{ss.analysis['price_median']:.0f} 元。")
        ss.hypos = I.build_hypotheses(merged, ss.insight["text_reviews"], band_order,
                                      use_llm=use_llm, ctx_summary=ctx_summary)
    else:
        ss.hypos = []
    ss.computed_key = computed_key

# ============================================================================
# 0 项目简介
# ============================================================================
if page.startswith("0"):
    st.title("AI 市场洞察与产品机会发现平台")
    mode = "大模型增强版" if use_llm else "规则版"
    st.markdown(f"""
    **AI Market Insight Copilot · V1.2.0（{mode}）**

    面向品类运营 / 采销、市场研究与产品经理，把分散的竞品参数与非结构化用户评价，
    转为**可追溯**的市场洞察与**待验证**的产品机会假设。当前演示场景为**移动电源**。

    **核心路径**：数据上传 → 数据质量校验 → 竞品与价格带分析 → 用户反馈主题洞察 → 产品机会假设 → 报告导出。

    **V1.2.0 特性**
    - 本地运行、浏览器操作，**无 API Key 也能用**（规则版）；
    - 支持 **CSV / Excel** 上传，自动**字段识别**（常见中/英表头别名映射）；
    - 主题识别采用**透明关键词规则**，情感采用**中文情感词典**，每条结论可回看原文证据 ID；
    - 配置 API Key 后可启用**大模型增强**（情感/主题/假设描述），但所有模型输出均标注为**待验证**；
    - 机会仅作**待验证假设**，不臆造销量、份额或市场结论。
    """)
    using_builtin = (ss.product_source.startswith("内置") and
                     ss.review_source.startswith("内置"))
    if using_builtin:
        st.info("⚠️ 当前使用模拟数据演示（source=synthetic），不代表真实市场；"
                "规则版未调用大模型，大模型增强版的输出也仅为辅助、待验证。", icon="📌")
    else:
        st.info("当前包含用户上传数据；请自行确认数据来源、授权和代表性。"
                "规则分析与模型增强输出均为辅助、待验证。", icon="📌")

# ============================================================================
# 1 数据上传与质量 (模块1)
# ============================================================================
elif page.startswith("1"):
    st.title("1 · 数据上传与质量校验 (模块1)")
    pr, rr = ss.prod_rep, ss.rev_rep
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("产品表")
        st.metric("总行数", pr["total"])
        st.metric("有效行", pr["valid"])
        st.metric("排除行", pr["excluded"])
        st.metric("去重移除", pr.get("duplicates_removed", 0))
    with c2:
        st.subheader("评价表")
        st.metric("总行数", rr["total"])
        st.metric("有效行", rr["valid"])
        st.metric("排除行", rr["excluded"])
        st.metric("去重移除", rr.get("duplicates_removed", 0))

    st.markdown(f"**分析所用样本量**：产品 {pr['valid']} 款、有效评价 {rr['valid']} 条"
                f"（空文本/外键不匹配/重复 ID 等已排除，不静默丢行）。")
    st.caption("字段识别：上传表头若为中文或常见变体（如 品牌/价格/容量/评分/评论），"
               "系统会自动映射到标准列名后再校验。")

    if pr["issues"]:
        st.error("产品表排除明细（不会静默丢行）：")
        st.table(pd.DataFrame(pr["issues"]))
    else:
        st.success("产品表校验通过，无排除行。")
    if rr["issues"]:
        st.error("评价表排除明细：")
        st.table(pd.DataFrame(rr["issues"]))
    else:
        st.success("评价表校验通过，无排除行。")
    if rr.get("warnings"):
        st.warning(f"部分有效提示（行保留，但相应分组剔除），共 {len(rr['warnings'])} 条：")
        with st.expander("查看提示明细"):
            for w in rr["warnings"][:50]:
                st.caption(w)

    st.subheader("校验后数据预览")
    with st.expander("查看产品表（有效行）"):
        st.dataframe(ss.prod_clean, width="stretch")
    with st.expander("查看评价表（有效行）"):
        st.dataframe(ss.rev_clean[["review_id", "product_id", "rating",
                                   "review_text", "review_date"]],
                     width="stretch")

# ============================================================================
# 2 竞品与价格带分析 (模块2)
# ============================================================================
elif page.startswith("2"):
    st.title("2 · 竞品与价格带分析 (模块2)")
    ana = ss.analysis
    if ana is None:
        st.warning("产品表无有效数据，无法分析。请检查上传数据或重新加载示例。")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("产品数", ana["n_products"])
        c2.metric("品牌数", ana["n_brands"])
        c3.metric("价格中位数(元)", f"{ana['price_median']:.1f}")
        miss = ana["missing"]
        st.caption(f"参数缺失：重量 {miss.get('weight_g',0)} 条、"
                   f"容量 {miss.get('capacity_mah',0)} 条、功率 {miss.get('power_w',0)} 条"
                   f"（缺失项不参与均值计算，不臆造）。")

        colA, colB = st.columns(2)
        with colA:
            st.subheader("价格带分布")
            st.bar_chart(ana["band_counts"])
        with colB:
            st.subheader("各价格带参数")
            st.dataframe(ana["band_stats"], width="stretch")

        st.subheader("品牌价格 / 属性对比")
        st.dataframe(ana["brand_attr"], width="stretch")
        try:
            import plotly.express as px
            st.bar_chart(ana["brand_price"].set_index("brand")["均价"])
        except Exception:
            pass

        st.subheader("参数 × 价格 散点（可按品牌/价格带筛选）")
        sc = ana["scatter"]
        brands = ["全部"] + sorted(sc["brand"].dropna().unique().tolist())
        sel_b = st.multiselect("品牌筛选", brands, default=["全部"])
        sel_bands = st.multiselect("价格带筛选", band_order, default=band_order)
        sc_f = sc.copy()
        if "全部" not in sel_b:
            sc_f = sc_f[sc_f["brand"].isin(sel_b)]
        sc_f = sc_f[sc_f["price_band"].isin(sel_bands)]
        if not sc_f.empty:
            try:
                import plotly.express as px
                fig = px.scatter(sc_f, x="price", y="capacity_mah",
                                 color="price_band", hover_data=["brand", "power_w", "weight_g"],
                                 size_max=18, title="价格 vs 容量（颜色=价格带）")
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.dataframe(sc_f, width="stretch")
        else:
            st.info("当前筛选无数据。")

        st.subheader("产品参数逐项对比")
        pids = ana["df"]["product_id"].tolist()
        sel_p = st.multiselect("选择要对比的商品（默认前 8 个）",
                               pids, default=pids[:8])
        cmp = A.compare_products(ana["df"], sel_p)
        st.dataframe(cmp, width="stretch")

# ============================================================================
# 3 用户反馈洞察 (模块3)
# ============================================================================
elif page.startswith("3"):
    st.title("3 · 用户反馈主题洞察 (模块3)")
    ins = ss.insight
    if ins is None:
        st.warning("评价表无有效数据，无法洞察。")
    else:
        st.markdown(f"- 参与文本洞察的有效评价：**{ins['n_text']}** 条　"
                    f"其中有效评分：**{ins['n_rated']}** 条　"
                    f"未命中任何主题：**{ins['unmatched']}** 条")
        ssum = ins.get("sentiment_summary", {})
        if ins.get("use_llm"):
            st.markdown(f"- 情感分布（大模型增强，实际调用模型标注 "
                        f"**{ins.get('llm_used', 0)}/{ins.get('llm_budget', 0)}** 条，"
                        f"其余回退中文情感词典）："
                        f"🟢正向 **{ssum.get('positive',0)}**　"
                        f"🔴负向 **{ssum.get('negative',0)}**　"
                        f"⚪中性 **{ssum.get('neutral',0)}**")
        else:
            st.markdown(f"- 情感分布（中文情感词典）："
                        f"🟢正向 **{ssum.get('positive',0)}**　"
                        f"🔴负向 **{ssum.get('negative',0)}**　"
                        f"⚪中性 **{ssum.get('neutral',0)}**")
        st.caption("说明：主题识别为透明关键词规则，情感为词典标注（LLM 启用时为增强标注），"
                   "均存在误判/漏判；一条评价可命中多主题，故各主题占比之和可 >100%。")

        ts = ins["theme_stats"]
        df_ts = pd.DataFrame(ts)
        st.subheader("主题频次与正负向")
        st.dataframe(df_ts, width="stretch")
        try:
            import plotly.express as px
            fig = px.bar(df_ts, x="theme", y="mentions", color="theme",
                         title="各主题提及数", text="pct")
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass

        st.subheader("主题 × 情感 热力图（定位投诉热点）")
        ts_mat = ins.get("theme_sentiment", [])
        if ts_mat:
            mat = pd.DataFrame(ts_mat).set_index("theme")[["positive", "negative", "neutral"]]
            try:
                import plotly.express as px
                fig2 = px.imshow(mat.values, x=["正向", "负向", "中性"], y=mat.index,
                                 text_auto=True, aspect="auto",
                                 color_continuous_scale="RdYlGn",
                                 title="主题 × 情感 计数（红=负向高）")
                st.plotly_chart(fig2, use_container_width=True)
            except Exception:
                st.dataframe(mat, width="stretch")
        else:
            st.info("暂无可绘制的热力图数据。")

        pains = ins.get("pain_points", [])
        if pains:
            st.subheader("痛点排序（按负向率，样本≥8）")
            for p in pains:
                st.markdown(f"- **{p['theme']}**：提及 {p['mentions']} 次，"
                            f"负向 {p['neg']} 次（负向率 {p['neg_rate']}%）")
        else:
            st.info("未检出足够样本量的显著痛点（各主题负向样本均 < 8 条）。")

        st.subheader("品牌用户反馈对比")
        brand_feedback = ins.get("brand_feedback", {})
        brand_summary = brand_feedback.get("summary", [])
        if brand_summary:
            st.caption(
                f"仅展示有效评价不少于 {brand_feedback.get('min_reviews', 3)} 条的品牌；"
                "负向率分母为该品牌全部有效文本评价。"
            )
            df_brand = pd.DataFrame(brand_summary).rename(columns={
                "brand": "品牌", "reviews": "评价数", "rated": "有效评分数",
                "negative": "负向数", "neg_rate": "负向率%",
                "avg_rating": "平均评分", "top_negative_theme": "首要负向主题",
                "top_negative_mentions": "该主题负向数",
            })
            st.dataframe(df_brand, width="stretch", hide_index=True)
            matrix_rows = brand_feedback.get("theme_matrix", [])
            if matrix_rows:
                matrix = pd.DataFrame(matrix_rows).set_index("brand")
                try:
                    import plotly.express as px
                    fig_brand = px.imshow(
                        matrix.values, x=matrix.columns, y=matrix.index,
                        text_auto=True, aspect="auto", color_continuous_scale="Reds",
                        labels={"x": "主题", "y": "品牌", "color": "占品牌评价%"},
                        title="品牌 × 负向主题提及率（占该品牌全部评价）",
                    )
                    st.plotly_chart(fig_brand, use_container_width=True)
                except Exception:
                    st.dataframe(matrix, width="stretch")
            excluded = brand_feedback.get("excluded_brands", [])
            if excluded:
                st.caption("样本不足、未参与品牌排序：" + "、".join(excluded))
        else:
            st.info("暂无达到最小评价样本量的品牌，暂不进行品牌负向率排序。")

        st.subheader("评价时间趋势")
        time_summary = ins.get("time_summary", {})
        monthly_trend = ins.get("monthly_trend", [])
        if monthly_trend:
            st.markdown(
                f"有效日期 **{time_summary.get('n_dated', 0)}** 条，覆盖 "
                f"**{time_summary.get('date_start')} 至 {time_summary.get('date_end')}**，"
                f"共 **{time_summary.get('n_months', 0)}** 个月。"
            )
            df_trend = pd.DataFrame(monthly_trend)
            try:
                from plotly.subplots import make_subplots
                import plotly.graph_objects as go

                fig_trend = make_subplots(specs=[[{"secondary_y": True}]])
                fig_trend.add_trace(
                    go.Bar(x=df_trend["month"], y=df_trend["reviews"],
                           name="评价量", marker_color="#2a9d8f"),
                    secondary_y=False,
                )
                fig_trend.add_trace(
                    go.Scatter(x=df_trend["month"], y=df_trend["neg_rate"],
                               name="负向率", mode="lines+markers",
                               line={"color": "#c1121f", "width": 3}),
                    secondary_y=True,
                )
                fig_trend.update_layout(title="月度评价量与负向率", hovermode="x unified")
                fig_trend.update_xaxes(title_text="月份", type="category")
                fig_trend.update_yaxes(title_text="评价量", secondary_y=False)
                fig_trend.update_yaxes(title_text="负向率（%）", range=[0, 100],
                                       secondary_y=True)
                st.plotly_chart(fig_trend, use_container_width=True)
            except Exception:
                st.dataframe(df_trend, width="stretch")
            with st.expander("查看月度趋势明细"):
                st.dataframe(df_trend, width="stretch")
            st.caption("时间趋势为描述性统计；月份样本量不同，负向率波动不代表因果或市场变化。")
        else:
            st.info("没有可用于时间趋势的有效评价日期。")

        st.subheader("查看原文证据")
        theme_names = [t["theme"] for t in ts]
        colT, colS, colB = st.columns(3)
        with colT:
            sel_t = st.selectbox("选择主题", theme_names)
        with colS:
            sel_s = st.selectbox("情感筛选（可选）",
                                 ["全部", "positive", "negative", "neutral"])
        brand_reviews = brand_feedback.get("brand_reviews")
        evidence_source = brand_reviews if isinstance(brand_reviews, pd.DataFrame) else ins["text_reviews"]
        with colB:
            brand_names = ["全部"] + sorted(evidence_source.get("brand", pd.Series(dtype=str)).dropna().unique().tolist())
            sel_brand = st.selectbox("品牌筛选（可选）", brand_names)
        if sel_brand != "全部":
            evidence_source = evidence_source[evidence_source["brand"] == sel_brand]
        ev = I.evidence_for(evidence_source, sel_t, limit=50,
                            sentiment=None if sel_s == "全部" else sel_s)
        if ev:
            st.markdown(f"命中 **{sel_t}** 的评价共 {len(ev)} 条（展示前 50）：")
            df_ev = pd.DataFrame(ev)
            st.dataframe(df_ev, width="stretch", height=320)
        else:
            st.info("该主题无命中记录。")

# ============================================================================
# 4 机会假设与导出 (模块4/5)
# ============================================================================
elif page.startswith("4"):
    st.title("4 · 产品机会假设与报告导出 (模块4/5)")
    hypos = ss.hypos
    ins = ss.insight
    if not hypos:
        st.warning("暂无可生成的假设（数据不足或评价未关联到价格带）。")
    else:
        for i, h in enumerate(hypos, 1):
            with st.expander(f"假设 {i}：{h['title']}"):
                st.write(h["detail"])
                st.caption(f"范围：{h['scope']}　样本量：{h['sample_size']}　"
                           f"可信度：{h['confidence']}")
                ev = h.get("evidence_ids") or []
                if ev:
                    st.markdown("证据评价 ID：" + "、".join(ev))

    st.markdown("---")
    st.subheader("生成报告")

    ctx = {
        "gen_time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "source_marker": f"产品：{ss.product_source}；评价：{ss.review_source}",
        "product_report": ss.prod_rep,
        "review_report": ss.rev_rep,
        "prod": ss.analysis or {},
        "insight": ins or {},
        "hypos": hypos,
        "use_llm": ss.get("use_llm", False),
        "band_order": band_order,
    }
    md = R.render_markdown(ctx)
    st.download_button("⬇ 下载 Markdown 报告", md.encode("utf-8-sig"),
                       file_name="market_insight_report.md", mime="text/markdown")

    figs = {}
    try:
        import plotly.express as px
        if ss.analysis:
            bc = ss.analysis["band_counts"]
            f1 = px.bar(x=list(bc.index), y=list(bc.values),
                        title="价格带分布", labels={"x": "价格带", "y": "产品数"})
            figs["band"] = f1.to_html(full_html=False, include_plotlyjs=True)
            bp = ss.analysis["brand_attr"]
            f2 = px.bar(bp, x="brand", y="均价", title="品牌均价对比")
            figs["brand"] = f2.to_html(full_html=False, include_plotlyjs=False)
        if ins:
            df_ts = pd.DataFrame(ins["theme_stats"])
            f3 = px.bar(df_ts, x="theme", y="mentions", title="主题提及数")
            include_js = not bool(figs)
            figs["theme"] = f3.to_html(full_html=False, include_plotlyjs=include_js)
            ts_mat = ins.get("theme_sentiment", [])
            if ts_mat:
                mat = pd.DataFrame(ts_mat).set_index("theme")[["positive", "negative", "neutral"]]
                f4 = px.imshow(mat.values, x=["正向", "负向", "中性"], y=mat.index,
                               text_auto=True, color_continuous_scale="RdYlGn",
                               title="主题 × 情感 热力图")
                figs["heat"] = f4.to_html(full_html=False, include_plotlyjs=False)
            monthly_trend = ins.get("monthly_trend", [])
            if monthly_trend:
                df_trend = pd.DataFrame(monthly_trend)
                f5 = px.line(df_trend, x="month", y="neg_rate", markers=True,
                             title="月度负向率（描述性统计）",
                             labels={"month": "月份", "neg_rate": "负向率（%）"})
                f5.update_xaxes(type="category")
                figs["trend"] = f5.to_html(full_html=False, include_plotlyjs=False)
            brand_feedback = ins.get("brand_feedback", {})
            matrix_rows = brand_feedback.get("theme_matrix", [])
            if matrix_rows:
                matrix = pd.DataFrame(matrix_rows).set_index("brand")
                f6 = px.imshow(
                    matrix.values, x=matrix.columns, y=matrix.index,
                    text_auto=True, aspect="auto", color_continuous_scale="Reds",
                    title="品牌 × 负向主题提及率",
                )
                figs["brand_feedback"] = f6.to_html(full_html=False, include_plotlyjs=False)
    except Exception:
        pass
    html = R.render_html(ctx, figs)
    st.download_button("⬇ 下载 HTML 报告（含图表）", html.encode("utf-8-sig"),
                       file_name="market_insight_report.html", mime="text/html")

    if ins:
        csv_ts = pd.DataFrame(ins["theme_stats"]).to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇ 下载主题频次 CSV", csv_ts.encode("utf-8-sig"),
                           file_name="theme_stats.csv", mime="text/csv")
        csv_ev = pd.DataFrame(
            [e for t in [I.evidence_for(ins["text_reviews"], x["theme"], 200) for x in ins["theme_stats"]]
             for e in t])
        if not csv_ev.empty:
            st.download_button("⬇ 下载原文证据 CSV", csv_ev.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                               file_name="evidence.csv", mime="text/csv")

    with st.expander("预览 Markdown 报告"):
        st.markdown(md)
