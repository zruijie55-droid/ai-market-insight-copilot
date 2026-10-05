"""竞品与价格带分析（对应 PRD F2）。

所有指标都来自用户上传/模拟的「参数」与「价格」，不臆造销量、市场份额或销售额。
价格带边界可在界面或此处配置（PRD 允许修改）。
"""
from __future__ import annotations

import pandas as pd
import numpy as np

# 默认价格带边界（元）。区间可在此或界面修改。
DEFAULT_BANDS = [
    (0, 99, "≤99"),
    (100, 199, "100–199"),
    (200, 299, "200–299"),
    (300, 10**9, "≥300"),
]


def build_price_bands(edge1: int, edge2: int, edge3: int) -> list[tuple[int, int, str]]:
    """根据三个上限生成连续价格带，并拒绝倒序或重复边界。"""
    edges = [edge1, edge2, edge3]
    if any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) for v in edges):
        raise ValueError("价格带边界必须是整数")
    if edge1 < 0:
        raise ValueError("第一档上限不能小于 0")
    if not edge1 < edge2 < edge3:
        raise ValueError("价格带边界必须严格递增：第一档 < 第二档 < 第三档")
    return [
        (0, edge1, f"≤{edge1}"),
        (edge1 + 1, edge2, f"{edge1 + 1}–{edge2}"),
        (edge2 + 1, edge3, f"{edge2 + 1}–{edge3}"),
        (edge3 + 1, 10**9, f"≥{edge3 + 1}"),
    ]


def price_band_label(price, bands=DEFAULT_BANDS) -> str:
    if pd.isna(price):
        return "未知"
    for lo, hi, label in bands:
        if lo <= price <= hi:
            return label
    return "未知"


def analyze_products(df: pd.DataFrame, bands=DEFAULT_BANDS) -> dict:
    """输入校验后的产品 clean_df，返回各项分析结构与图表用数据。

    返回 dict 键：
      n_products, n_brands, price_median, missing(各列缺失数),
      band_order, band_counts(Series), band_stats(DataFrame),
      brand_price(DataFrame), scatter(DataFrame 含 price/capacity/power/weight/band)
    """
    df = df.copy()
    df["price_band"] = df["price"].apply(lambda x: price_band_label(x, bands))
    band_order = [b[2] for b in bands]

    n_products = len(df)
    n_brands = int(df["brand"].nunique(dropna=True))
    price_median = df["price"].median()
    missing = {c: int(df[c].isna().sum())
               for c in ["weight_g", "capacity_mah", "power_w", "price"]}

    band_counts = (df["price_band"].value_counts()
                   .reindex(band_order).fillna(0).astype(int))

    band_stats = (df.groupby("price_band")
                  .agg(产品数=("product_id", "count"),
                       均价=("price", "mean"),
                       容量中位=("capacity_mah", "median"),
                       功率中位=("power_w", "median"),
                       重量缺失=("weight_g", lambda s: int(s.isna().sum())))
                  .reindex(band_order))
    for c in ["产品数", "均价", "容量中位", "功率中位", "重量缺失"]:
        band_stats[c] = pd.to_numeric(band_stats[c], errors="coerce")
    band_stats["产品数"] = band_stats["产品数"].fillna(0).astype(int)
    band_stats["均价"] = band_stats["均价"].round(1)
    band_stats["重量缺失"] = band_stats["重量缺失"].fillna(0).astype(int)

    brand_price = (df.groupby("brand")["price"]
                   .agg(产品数="count", 均价="mean", 中位价="median")
                   .reset_index().sort_values("均价", ascending=False))
    for c in ["产品数", "均价", "中位价"]:
        brand_price[c] = pd.to_numeric(brand_price[c], errors="coerce")
    brand_price["产品数"] = brand_price["产品数"].fillna(0).astype(int)
    brand_price["均价"] = brand_price["均价"].round(1)
    brand_price["中位价"] = brand_price["中位价"].round(1)

    scatter = df[["product_id", "brand", "price", "capacity_mah",
                  "power_w", "weight_g", "price_band"]].copy()

    # 品牌维度参数对比（均值，缺失不参与）
    brand_attr = (df.groupby("brand")
                  .agg(产品数=("product_id", "count"),
                       均价=("price", "mean"),
                       平均容量=("capacity_mah", "mean"),
                       平均功率=("power_w", "mean"),
                       平均重量=("weight_g", "mean"))
                  .reset_index().sort_values("均价", ascending=False))
    for c in ["均价", "平均容量", "平均功率", "平均重量"]:
        brand_attr[c] = pd.to_numeric(brand_attr[c], errors="coerce")
        brand_attr[c] = brand_attr[c].round(1)
    brand_attr["产品数"] = pd.to_numeric(
        brand_attr["产品数"], errors="coerce").fillna(0).astype(int)

    return {
        "n_products": n_products,
        "n_brands": n_brands,
        "price_median": price_median,
        "missing": missing,
        "band_order": band_order,
        "band_counts": band_counts,
        "band_stats": band_stats,
        "brand_price": brand_price,
        "brand_attr": brand_attr,
        "scatter": scatter,
        "df": df,
    }


def compare_products(df: pd.DataFrame, product_ids: list = None) -> pd.DataFrame:
    """选定商品逐项参数对比（模块2『产品参数对比』）。

    返回按价格升序的 DataFrame，列为 品牌 / 商品名称 / 价格 / 容量(mAh) /
    功率(W) / 重量(g) / 价格带。product_ids 为空时返回全部。
    """
    sub = df.copy()
    if product_ids:
        sub = sub[sub["product_id"].isin(product_ids)]
    cols = ["product_id", "brand", "product_name", "price", "capacity_mah",
            "power_w", "weight_g", "price_band"]
    cols = [c for c in cols if c in sub.columns]
    out = sub[cols].sort_values("price").reset_index(drop=True)
    return out


def merge_review_rating(products_df: pd.DataFrame, reviews_df: pd.DataFrame,
                        bands=DEFAULT_BANDS) -> pd.DataFrame:
    """把评价表关联到产品表，得到每条评价的价格带（用于 F3/F4 分层）。

    仅保留有有效评分的评价；无评分的评价不进入此表（避免零分母）。
    """
    r = reviews_df[reviews_df["rating_valid"] == True].copy()
    if r.empty:
        return r
    p = products_df[["product_id", "price"]].copy()
    p["price_band"] = p["price"].apply(lambda x: price_band_label(x, bands))
    merged = r.merge(p[["product_id", "price_band"]], on="product_id", how="left")
    return merged
