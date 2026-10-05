"""规则版用户反馈主题洞察（对应 PRD F3 / F4）。

设计要点：
- 透明关键词基线：主题与关键词完全可解释、可审计，不调用大模型；
- 一条评价可命中多个主题（因此主题占比可相加 >100%）；
- 情感采用**中文情感词典**（src.sentiment，VADER 风格的中文适配），在 LLM 可用且
  用户显式启用时，可叠加大模型情感判断（src.llm）作为增强，二者都只是辅助标注；
- 新增「主题 × 情感」矩阵与「痛点排序」，借鉴参考项目的主题×情感热力图思路，
  用于定位负面反馈集中的主题（投诉热点）；
- 明确统计「未识别主题」条数，提示规则局限；
- 机会假设全部为「待验证假设」，标注样本量/范围/证据 ID，绝不给出市场结论。
"""
from __future__ import annotations

import pandas as pd

from . import sentiment as SENT

try:
    from . import llm as LLM
except Exception:  # pragma: no cover
    LLM = None

# (主题, 关键词) —— 透明、可审计的规则基线
THEMES = [
    ("便携/重量", ["便携", "轻便", "小巧", "体积", "携带", "太重", "很重", "偏重",
                "沉重", "压手", "轻巧", "沉甸甸", "不重"]),
    ("容量/续航", ["容量", "续航", "电量", "毫安", "耐用", "用得久", "不够用",
                "不耐用", "虚标", "续航短", "掉电"]),
    ("充电速度", ["充电快", "快充", "充得快", "充电慢", "充电速度", "回血",
                "充不进", "充不进去", "充电口"]),
    ("发热", ["发热", "发烫", "烫手", "高温", "过热"]),
    ("安全感", ["安全", "爆炸", "起火", "自燃", "鼓包", "危险", "放心",
              "靠谱", "质量", "用料"]),
    ("价格", ["便宜", "贵", "性价比", "价格", "划算", "值", "实惠", "不值", "价位"]),
    ("外观", ["外观", "好看", "颜值", "设计", "漂亮", "美观", "丑", "造型"]),
]


def classify(text: str) -> list[str]:
    """返回命中的主题名列表（一条评价可命中多个）。"""
    if not isinstance(text, str) or not text.strip():
        return []
    return [name for name, kws in THEMES if any(k in text for k in kws)]


def _sentiment_label(text: str, use_llm: bool) -> str:
    """情感标注：默认规则版；use_llm 且可用时尝试大模型，异常回退规则。"""
    if use_llm and LLM is not None and LLM.is_available():
        try:
            return LLM.llm_sentiment(text)
        except Exception:
            pass
    return SENT.label(text)


def analyze_reviews(reviews_df: pd.DataFrame, use_llm: bool = False) -> dict:
    """输入校验后的评价 clean_df（需含 review_text, rating_valid, rating, review_id, product_id）。

    返回：
      n_text        : 参与文本洞察的有效评价数（非空文本）
      n_rated       : 其中有有效评分的
      unmatched     : 文本非空但未命中任何主题的评价数
      sentiment_summary : {positive, negative, neutral} 计数
      theme_stats   : list[dict]，每主题 {theme, mentions, pct, low, high, neutral,
                      unrated, pos, neg, neutral_s, neg_rate}
      theme_sentiment : list[dict]，主题×情感矩阵（热力图用）
      pain_points  : list[dict]，按负面率排序的痛点（min mentions>=8）
      time_summary : 有效日期数、日期范围和月份数
      monthly_trend: 月度评价量、情感计数、负向率和平均评分
      text_reviews  : 带 themes / sentiment 列的 DataFrame（供证据检索）
      use_llm       : 本次分析是否启用了大模型增强
      llm_used      : 本次实际走大模型情感标注的评价条数（费用控制：≤ MAX_LLM_REVIEWS）
      llm_budget    : 本次允许的大模型标注上限
    """
    text_df = reviews_df[reviews_df["text_valid"] == True].copy()
    n_text = len(text_df)
    # 实际生效的 LLM 标志：仅当调用方要求且确实配置了 Key 时才为 True
    effective_llm = bool(use_llm and LLM is not None and LLM.is_available())
    if n_text == 0:
        # 空数据提前返回零值，避免对空 DataFrame 做布尔索引导致列丢失
        empty_ts = [{"theme": name, "mentions": 0, "pct": 0.0,
                     "low": 0, "high": 0, "neutral": 0, "unrated": 0,
                     "pos": 0, "neg": 0, "neutral_s": 0, "neg_rate": 0.0}
                    for name, _ in THEMES]
        return {
            "n_text": 0, "n_rated": 0, "unmatched": 0,
            "sentiment_summary": {"positive": 0, "negative": 0, "neutral": 0},
            "theme_stats": empty_ts, "theme_sentiment": [], "pain_points": [],
            "time_summary": {"n_dated": 0, "date_start": None,
                             "date_end": None, "n_months": 0},
            "monthly_trend": [],
            "text_reviews": text_df, "use_llm": effective_llm, "llm_used": 0,
            "llm_budget": 0,
        }

    # 费用控制：大模型情感标注最多处理 MAX_LLM_REVIEWS 条，其余自动回退规则版，
    # 避免在大量评价下一不小心产生高额 token 费用。
    llm_budget = LLM.MAX_LLM_REVIEWS if (effective_llm and LLM is not None) else 0
    llm_used = 0

    def _label_with_budget(t: str) -> str:
        nonlocal llm_used
        if llm_budget and llm_used < llm_budget:
            llm_used += 1
            return _sentiment_label(t, True)
        return SENT.label(t)

    text_df["sentiment"] = text_df["review_text"].apply(_label_with_budget)
    text_df["themes"] = text_df["review_text"].apply(classify)
    text_df["n_themes"] = text_df["themes"].apply(len)

    n_rated = int(text_df["rating_valid"].sum())
    unmatched = int((text_df["n_themes"] == 0).sum())

    stats = []
    for name, _ in THEMES:
        sub = text_df[text_df["themes"].apply(lambda L: name in L)]
        n = len(sub)
        rated = sub[sub["rating_valid"] == True]
        low = int((rated["rating"] <= 2).sum())
        high = int((rated["rating"] >= 4).sum())
        neu = int((rated["rating"] == 3).sum())
        pos = int((sub["sentiment"] == "positive").sum())
        neg = int((sub["sentiment"] == "negative").sum())
        neu_s = int((sub["sentiment"] == "neutral").sum())
        stats.append({
            "theme": name, "mentions": n,
            "pct": round(100 * n / n_text, 1) if n_text else 0.0,
            "low": low, "high": high, "neutral": neu, "unrated": n - len(rated),
            "pos": pos, "neg": neg, "neutral_s": neu_s,
            "neg_rate": round(100 * neg / n, 1) if n else 0.0,
        })

    s_counts = text_df["sentiment"].value_counts().to_dict()
    sentiment_summary = {
        "positive": int(s_counts.get("positive", 0)),
        "negative": int(s_counts.get("negative", 0)),
        "neutral": int(s_counts.get("neutral", 0)),
    }
    theme_sentiment = [{"theme": t["theme"], "positive": t["pos"],
                        "negative": t["neg"], "neutral": t["neutral_s"]} for t in stats]
    # 痛点：负面率降序，至少被提及 8 次，避免小样本误判
    pain_points = sorted(
        [t for t in stats if t["mentions"] >= 8],
        key=lambda x: -x["neg_rate"])[:5]
    pain_points = [{"theme": t["theme"], "mentions": t["mentions"],
                    "neg": t["neg"], "neg_rate": t["neg_rate"]} for t in pain_points]

    # 时间趋势只使用日期有效的评价。它是描述性统计，不把月份波动解释为因果或市场趋势。
    if "date_valid" in text_df and "review_date" in text_df:
        dated = text_df[text_df["date_valid"].eq(True) &
                        text_df["review_date"].notna()].copy()
    else:
        dated = text_df.iloc[0:0].copy()
    monthly_trend = []
    if not dated.empty:
        dated["review_date"] = pd.to_datetime(dated["review_date"], errors="coerce")
        dated = dated[dated["review_date"].notna()].copy()
    if not dated.empty:
        dated["month"] = dated["review_date"].dt.to_period("M").astype(str)
        dated["rating_for_avg"] = pd.to_numeric(
            dated["rating"].where(dated["rating_valid"].eq(True)), errors="coerce"
        )
        for month, group in dated.groupby("month", sort=True):
            n_month = len(group)
            negative = int(group["sentiment"].eq("negative").sum())
            avg_rating = group["rating_for_avg"].mean()
            monthly_trend.append({
                "month": month,
                "reviews": n_month,
                "positive": int(group["sentiment"].eq("positive").sum()),
                "negative": negative,
                "neutral": int(group["sentiment"].eq("neutral").sum()),
                "neg_rate": round(100 * negative / n_month, 1),
                "avg_rating": round(float(avg_rating), 2) if pd.notna(avg_rating) else None,
            })
        time_summary = {
            "n_dated": len(dated),
            "date_start": dated["review_date"].min().strftime("%Y-%m-%d"),
            "date_end": dated["review_date"].max().strftime("%Y-%m-%d"),
            "n_months": len(monthly_trend),
        }
    else:
        time_summary = {"n_dated": 0, "date_start": None,
                        "date_end": None, "n_months": 0}

    return {
        "n_text": n_text, "n_rated": n_rated, "unmatched": unmatched,
        "sentiment_summary": sentiment_summary,
        "theme_stats": stats, "theme_sentiment": theme_sentiment,
        "pain_points": pain_points,
        "time_summary": time_summary, "monthly_trend": monthly_trend,
        "text_reviews": text_df, "use_llm": effective_llm,
        "llm_used": llm_used, "llm_budget": llm_budget,
    }


def evidence_for(text_reviews: pd.DataFrame, theme: str, limit: int = 30,
                 sentiment: str = None) -> list[dict]:
    """返回命中某主题的评价原文证据（含 review_id/product_id/rating/sentiment/text）。"""
    sub = text_reviews[text_reviews["themes"].apply(lambda L: theme in L)]
    if sentiment:
        sub = sub[sub["sentiment"] == sentiment]
    out = []
    for _, r in sub.head(limit).iterrows():
        out.append({
            "review_id": r.get("review_id"),
            "product_id": r.get("product_id"),
            "brand": r.get("brand"),
            "rating": int(r["rating"]) if pd.notna(r.get("rating")) else None,
            "sentiment": r.get("sentiment", "neutral"),
            "text": r.get("review_text", ""),
        })
    return out


def analyze_brand_feedback(products_df: pd.DataFrame, text_reviews: pd.DataFrame,
                           min_reviews: int = 3) -> dict:
    """把评价关联回品牌，生成带最小样本门槛的品牌反馈对比。"""
    empty = {
        "min_reviews": min_reviews, "linked_reviews": 0, "eligible_brands": 0,
        "excluded_brands": [], "summary": [], "theme_matrix": [],
        "brand_reviews": text_reviews.iloc[0:0].copy(),
    }
    if products_df.empty or text_reviews.empty:
        return empty
    required_products = {"product_id", "brand"}
    required_reviews = {"product_id", "sentiment", "themes", "rating", "rating_valid"}
    if not required_products.issubset(products_df.columns) or not required_reviews.issubset(text_reviews.columns):
        return empty

    brand_map = products_df[["product_id", "brand"]].drop_duplicates("product_id").copy()
    brand_map["brand"] = brand_map["brand"].fillna("").astype(str).str.strip()
    brand_map.loc[brand_map["brand"].eq(""), "brand"] = "未知品牌"
    linked = text_reviews.merge(brand_map, on="product_id", how="inner")
    if linked.empty:
        return empty

    counts = linked.groupby("brand").size().sort_values(ascending=False)
    eligible = counts[counts >= min_reviews].index.tolist()
    excluded = counts[counts < min_reviews].index.tolist()
    summary = []
    matrix = []
    for brand in eligible:
        group = linked[linked["brand"] == brand]
        n_reviews = len(group)
        negative = int(group["sentiment"].eq("negative").sum())
        rated = group[group["rating_valid"].eq(True)]
        avg_rating = pd.to_numeric(rated["rating"], errors="coerce").mean()
        neg_group = group[group["sentiment"].eq("negative")]
        theme_negative = {
            name: int(neg_group["themes"].apply(lambda values: name in values).sum())
            for name, _ in THEMES
        }
        top_theme, top_count = max(theme_negative.items(), key=lambda item: item[1])
        summary.append({
            "brand": brand,
            "reviews": n_reviews,
            "rated": len(rated),
            "negative": negative,
            "neg_rate": round(100 * negative / n_reviews, 1),
            "avg_rating": round(float(avg_rating), 2) if pd.notna(avg_rating) else None,
            "top_negative_theme": top_theme if top_count else "无明显负向主题",
            "top_negative_mentions": top_count,
        })
        matrix.append({
            "brand": brand,
            **{name: round(100 * count / n_reviews, 1)
               for name, count in theme_negative.items()},
        })

    summary.sort(key=lambda item: (-item["neg_rate"], -item["reviews"], item["brand"]))
    matrix_order = {item["brand"]: i for i, item in enumerate(summary)}
    matrix.sort(key=lambda item: matrix_order[item["brand"]])
    return {
        "min_reviews": min_reviews,
        "linked_reviews": len(linked),
        "eligible_brands": len(eligible),
        "excluded_brands": excluded,
        "summary": summary,
        "theme_matrix": matrix,
        "brand_reviews": linked,
    }


def build_hypotheses(merged: pd.DataFrame, text_reviews: pd.DataFrame,
                     bands_order: list[str], min_low: int = 8,
                     use_llm: bool = False, ctx_summary: str = "") -> list[dict]:
    """基于可解释规则生成「待验证」机会假设。

    merged: 评价关联到价格带后的表（含 rating_valid, rating, price_band, themes 列）
    text_reviews: 含 themes / sentiment 列的 DataFrame
    use_llm: 是否用大模型润色假设描述（仍标注为待验证）
    """
    hypos = []
    n_text = len(text_reviews)
    if n_text == 0:
        hypos.append({
            "title": "无有效评价文本",
            "detail": "当前样本无可用于主题洞察的评价文本，无法形成假设。请上传更多带文本的评价。",
            "scope": "全部", "sample_size": 0, "evidence_ids": [],
            "confidence": "不适用",
        })
        return hypos

    if merged.empty:
        for name, _ in THEMES:
            sub = text_reviews[text_reviews["themes"].apply(lambda L: name in L)]
            if len(sub) == 0:
                continue
            hypos.append({
                "title": f"主题「{name}」共提及 {len(sub)} 次（全样本）",
                "detail": "当前评价未能关联到价格带（缺少有效评分或产品匹配），仅给出全样本主题频次，无法做价格带细分假设。",
                "scope": "全样本（无价格带）", "sample_size": n_text,
                "evidence_ids": [r for r in sub["review_id"].head(3).tolist()],
                "confidence": "描述性，非结论",
            })
        return hypos

    band_map = merged.drop_duplicates("product_id")[["product_id", "price_band"]]
    tr = text_reviews.merge(band_map, on="product_id", how="left")

    for band in bands_order:
        band_text = tr[tr["price_band"] == band]
        n_band = len(band_text)
        if n_band == 0:
            continue
        rated_band = band_text[band_text["rating_valid"] == True]
        low_band = rated_band[rated_band["rating"] <= 2]
        n_low = len(low_band)
        if n_low < min_low:
            continue
        for name, _ in THEMES:
            sub_band = band_text[band_text["themes"].apply(lambda L: name in L)]
            sub_low = low_band[low_band["themes"].apply(lambda L: name in L)]
            overall_rate = len(sub_band) / n_band
            low_rate = len(sub_low) / n_low
            if low_rate >= 0.20 and low_rate > overall_rate * 1.15 and len(sub_low) >= 2:
                ev = sub_low["review_id"].head(3).tolist()
                h = {
                    "title": f"在「{band}」价格带，低分评价中「{name}」提及率偏高",
                    "detail": (f"该价格带有 {n_band} 条有效评价，其中低分（1–2 星）{n_low} 条；"
                               f"低分评价里「{name}」提及率约 {round(100 * low_rate, 1)}%，"
                               f"高于该价格带整体提及率 {round(100 * overall_rate, 1)}%。"
                               f"建议作为『待验证假设』开展轻量化需求验证，"
                               f"例如针对「{name}」做小样本用户访谈或 A/B，"
                               f"确认是否存在未被满足的需求。"),
                    "scope": f"价格带 {band}", "sample_size": n_low, "evidence_ids": ev,
                    "confidence": f"基于规则统计（低分样本 {n_low} 条，≥{min_low} 阈值），仅为假设，需进一步验证",
                }
                hypos.append(_maybe_llm_enrich(h, use_llm, ctx_summary))
    if not hypos:
        hypos.append({
            "title": "未触发显著假设规则",
            "detail": ("当前样本中，各价格带低分评价的主题提及率未明显高于整体，"
                       "或低分样本量不足（< %d 条）。这不代表市场无机会，"
                       "仅说明按既定规则未检出强信号，建议结合人工研判或扩充样本。" % min_low),
            "scope": "全部价格带", "sample_size": n_text, "evidence_ids": [],
            "confidence": "规则未触发",
        })
    return hypos


def _maybe_llm_enrich(hypo: dict, use_llm: bool, ctx_summary: str) -> dict:
    """可选：用大模型润色假设描述（仍标注为待验证）。失败则保留规则版。"""
    if not (use_llm and LLM is not None and LLM.is_available()):
        return hypo
    try:
        narr = LLM.llm_opportunity_narrative(hypo["title"], hypo["detail"], ctx_summary)
        if narr and len(narr) > 10:
            hypo = dict(hypo)
            hypo["detail"] = narr + "\n\n（以上为模型辅助生成的表述，仍属待验证假设。）"
    except Exception:
        pass
    return hypo
