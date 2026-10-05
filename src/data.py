"""数据加载与质量校验（对应 PRD F1）。

设计原则：
- 不静默丢弃任何行：被排除的行会记录「行号 / 字段 / 原因」，并在 UI 展示；
- 缺失评分、缺失日期属于「部分有效」，行保留但计入提示，仅在对应分组中剔除；
- 空评价文本、外键不匹配、重复 ID、无效数值 属于「整行排除」，不进入下游分析；
- 返回的 clean DataFrame 已把数值列转换为正确类型，供下游直接使用。
"""
from __future__ import annotations

import io
import os

import pandas as pd
from pathlib import Path

PRODUCT_REQUIRED = ["product_id", "brand", "product_name", "price",
                    "capacity_mah", "power_w", "source"]
REVIEW_REQUIRED = ["review_id", "product_id", "rating", "review_text",
                   "review_date", "source"]

# 列名别名映射（字段识别）：兼容中文表头 / 常见英文变体
PRODUCT_ALIASES = {
    "商品id": "product_id", "产品id": "product_id", "id": "product_id",
    "品牌": "brand", "brand_name": "brand",
    "商品名": "product_name", "产品名": "product_name", "名称": "product_name",
    "价格": "price", "售价": "price", "标价": "price",
    "容量": "capacity_mah", "容量mah": "capacity_mah", "电池容量": "capacity_mah",
    "功率": "power_w", "充电功率": "power_w",
    "重量": "weight_g", "毛重": "weight_g",
    "来源": "source", "数据源": "source",
}
REVIEW_ALIASES = {
    "评价id": "review_id", "评论id": "review_id",
    "商品id": "product_id", "产品id": "product_id",
    "评分": "rating", "星级": "rating", "打分": "rating",
    "评价内容": "review_text", "评论": "review_text", "内容": "review_text", "正文": "review_text",
    "日期": "review_date", "评价日期": "review_date", "时间": "review_date",
    "来源": "source",
}


def _is_file_like(obj) -> bool:
    """判断是否为「类文件对象」（如 Streamlit 的 UploadedFile），而非路径。

    UploadedFile 是 io.BytesIO 的子类，支持 read()/getvalue()/seek()，
    但没有真实的文件系统路径，因此不能用 Path() 处理。
    """
    if isinstance(obj, (str, bytes, os.PathLike)):
        return False
    return hasattr(obj, "read")


def _read_bytes(file_like) -> bytes:
    """从类文件对象安全读取全部字节，且不破坏其当前读取位置。"""
    if hasattr(file_like, "getvalue"):
        return bytes(file_like.getvalue())
    pos = file_like.tell()
    try:
        return file_like.read()
    finally:
        try:
            file_like.seek(pos)
        except Exception:
            pass


def _read_csv_bytes(content: bytes) -> pd.DataFrame:
    """从字节内容读取 CSV，兼容 UTF-8-SIG / UTF-8 / GBK（Windows 常见编码）。"""
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=enc, dtype=str)
        except UnicodeDecodeError as e:
            last_err = e
            continue
    # 最后一次交给 pandas 报错
    if last_err is None:
        return pd.read_csv(io.BytesIO(content), dtype=str)
    raise last_err


def load_csv(path) -> pd.DataFrame:
    """读取 CSV，兼容 UTF-8-SIG / UTF-8 / GBK（Windows 常见编码）。

    支持：本地路径（str / Path）或类文件对象（如 Streamlit UploadedFile）。
    """
    if _is_file_like(path):
        return _read_csv_bytes(_read_bytes(path))
    p = Path(path)
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return pd.read_csv(p, encoding=enc, dtype=str)
        except UnicodeDecodeError as e:
            last_err = e
            continue
    # 最后一次交给 pandas 报错
    if last_err is None:
        return pd.read_csv(p, dtype=str)
    raise last_err


def load_any(path) -> pd.DataFrame:
    """自动按扩展名读取 CSV 或 Excel（.xlsx/.xls）。Excel 需要 openpyxl。

    同时支持：
    - 文件路径（str / Path）；
    - 类文件对象（如 Streamlit st.file_uploader 返回的 UploadedFile）。
    对类文件对象，从 .name 属性推断扩展名；无法推断时默认按 CSV 读取。
    """
    if _is_file_like(path):
        name = getattr(path, "name", "") or ""
        suffix = Path(name).suffix.lower()
        content = _read_bytes(path)
        if suffix in (".xlsx", ".xls"):
            try:
                return pd.read_excel(io.BytesIO(content), dtype=str)
            except ImportError:
                raise ImportError("读取 Excel 需要安装 openpyxl：pip install openpyxl")
        return _read_csv_bytes(content)
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        try:
            return pd.read_excel(p, dtype=str)
        except ImportError:
            raise ImportError("读取 Excel 需要安装 openpyxl：pip install openpyxl")
    return load_csv(p)


def normalize_columns(df: pd.DataFrame, aliases: dict) -> pd.DataFrame:
    """按别名映射把表头规范化为标准列名（字段识别）。

    只重命名存在的别名列，避免覆盖已有标准列。返回新 DataFrame。
    """
    df = df.copy()
    rename = {c: aliases[c] for c in df.columns if c in aliases and aliases[c] not in df.columns}
    if rename:
        df = df.rename(columns=rename)
    return df


def _to_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def validate_products(df: pd.DataFrame):
    """返回 (clean_df, report)。

    clean_df 列：product_id, brand, product_name, price(float),
    capacity_mah(int), power_w(float), weight_g(float|NaN), source
    report: {total, valid, excluded, issues[], valid_ids:set}
    """
    issues = []
    total = len(df)
    if df.empty:
        return df, {"total": 0, "valid": 0, "excluded": 0, "issues": issues, "valid_ids": set()}

    missing_cols = [c for c in PRODUCT_REQUIRED if c not in df.columns]
    if missing_cols:
        issues.append({"row": "-", "field": ",".join(missing_cols),
                       "reason": f"缺少必填列：{','.join(missing_cols)}，无法继续产品表分析"})
        return df.iloc[0:0], {"total": total, "valid": 0, "excluded": total,
                              "duplicates_removed": 0,
                              "issues": issues, "valid_ids": set()}

    work = df.copy()
    # 先处理缺失值再转字符串（避免 NaN→"nan" 字符串被误判）
    work["product_id"] = work["product_id"].fillna("").astype(str).str.strip()
    work["brand"] = work["brand"].fillna("").astype(str).str.strip()
    price = _to_float(work["price"])
    dup_removed = 0
    cap = _to_float(work["capacity_mah"])
    pwr = _to_float(work["power_w"])
    wgt = _to_float(work["weight_g"])

    keep = pd.Series([True] * len(work))
    reason = pd.Series([""] * len(work))
    first_idx = {}  # product_id -> 首次出现行号
    for i in range(len(work)):
        pid = work["product_id"].iat[i]
        if pid not in ("", "nan", "None"):
            first_idx.setdefault(pid, i)

    for i in range(len(work)):
        pid = work["product_id"].iat[i]
        prob = []
        if pid in ("", "nan", "None"):
            prob.append("product_id 为空")
            keep.iat[i] = False
        elif i != first_idx.get(pid, i):
            prob.append(f"product_id 重复（首次出现在第 {first_idx.get(pid)} 行）")
            keep.iat[i] = False
            dup_removed += 1
        p = price.iat[i]
        if pd.isna(p) or p < 0:
            prob.append(f"price 无效（{work['price'].iat[i]}）")
            keep.iat[i] = False
        c = cap.iat[i]
        if pd.isna(c) or c <= 0 or float(c) != int(c):
            prob.append(f"capacity_mah 无效（{work['capacity_mah'].iat[i]}）")
            keep.iat[i] = False
        pw = pwr.iat[i]
        if pd.isna(pw) or pw <= 0:
            prob.append(f"power_w 无效（{work['power_w'].iat[i]}）")
            keep.iat[i] = False
        w = wgt.iat[i]
        if not pd.isna(w) and w < 0:
            prob.append(f"weight_g 为负（{work['weight_g'].iat[i]}）")
            keep.iat[i] = False
        reason.iat[i] = "；".join(prob)

    for i in range(len(work)):
        if not keep.iat[i]:
            issues.append({"row": i + 2, "field": "行", "reason": reason.iat[i]})

    clean = work[keep].copy()
    clean["price"] = _to_float(clean["price"]).astype(float)
    clean["capacity_mah"] = _to_float(clean["capacity_mah"]).astype(int)
    clean["power_w"] = _to_float(clean["power_w"]).astype(float)
    clean["weight_g"] = _to_float(clean["weight_g"])
    valid_ids = set(clean["product_id"].tolist())
    report = {"total": total, "valid": int(keep.sum()),
              "excluded": int((~keep).sum()), "duplicates_removed": dup_removed,
              "issues": issues, "valid_ids": valid_ids}
    return clean, report


def _parse_date(s):
    if s is None:
        return pd.NaT
    s = str(s).strip()
    if s in ("", "nan", "None"):
        return pd.NaT
    return pd.to_datetime(s, errors="coerce")


def validate_reviews(df: pd.DataFrame, valid_product_ids: set):
    """返回 (clean_df, report)。

    clean_df 列：review_id, product_id, rating(int|NaN), review_text(str),
    review_date(datetime|NaT), source, rating_valid(bool), date_valid(bool),
    text_valid(bool)
    - 整行排除：review_id 空/重复、product_id 不在 valid_product_ids、review_text 空；
    - 部分有效（保留并提示）：rating 缺失/越界 → rating_valid=False；
      review_date 缺失/不可解析 → date_valid=False。
    """
    issues = []
    warnings = []
    total = len(df)
    if df.empty:
        return df, {"total": 0, "valid": 0, "excluded": 0,
                    "issues": issues, "warnings": warnings}

    missing_cols = [c for c in REVIEW_REQUIRED if c not in df.columns]
    if missing_cols:
        issues.append({"row": "-", "field": ",".join(missing_cols),
                       "reason": f"缺少必填列：{','.join(missing_cols)}，无法继续评价表分析"})
        return df.iloc[0:0], {"total": total, "valid": 0, "excluded": total,
                              "duplicates_removed": 0,
                              "issues": issues, "warnings": warnings}

    work = df.copy()
    # 关键：先处理缺失值（NaN/None），再转字符串。否则 astype(str) 会把 NaN 变成
    # 字面量 "nan" 字符串，使空评价被误判为有效文本（数据清洗错误）。
    work["review_id"] = work["review_id"].fillna("").astype(str).str.strip()
    work["product_id"] = work["product_id"].fillna("").astype(str).str.strip()
    work["review_text"] = work["review_text"].fillna("").astype(str).str.strip()
    rating_raw = work["rating"]
    dup_removed = 0
    rating_num = _to_float(rating_raw)
    work["rating_valid"] = rating_num.apply(
        lambda x: (not pd.isna(x)) and (1 <= x <= 5) and (float(x) == int(x)))
    work["rating"] = rating_num.apply(lambda x: int(x) if (not pd.isna(x)) and (1 <= x <= 5) else pd.NA)
    work["date_valid"] = work["review_date"].apply(lambda x: _parse_date(x) is not pd.NaT)
    work["review_date"] = work["review_date"].apply(_parse_date)
    work["text_valid"] = work["review_text"].apply(lambda t: isinstance(t, str) and len(t) > 0)

    keep = pd.Series([True] * len(work))
    reason = pd.Series([""] * len(work))
    first_idx = {}
    for i in range(len(work)):
        rid = work["review_id"].iat[i]
        if rid not in ("", "nan", "None"):
            first_idx.setdefault(rid, i)

    for i in range(len(work)):
        rid = work["review_id"].iat[i]
        pid = work["product_id"].iat[i]
        prob = []
        if rid in ("", "nan", "None"):
            prob.append("review_id 为空"); keep.iat[i] = False
        elif i != first_idx.get(rid, i):
            prob.append(f"review_id 重复（首次出现在第 {first_idx.get(rid)} 行）"); keep.iat[i] = False
            dup_removed += 1
        if pid not in valid_product_ids:
            prob.append(f"外键不匹配：product_id={pid} 不在产品表有效列表中"); keep.iat[i] = False
        if not work["text_valid"].iat[i]:
            prob.append("评价文本为空，不参与文本洞察"); keep.iat[i] = False
        # 部分有效提示
        if keep.iat[i]:
            if not work["rating_valid"].iat[i]:
                warnings.append(f"R={rid}：评分缺失或越界（{rating_raw.iat[i]}），评分分组中剔除")
            if not work["date_valid"].iat[i]:
                warnings.append(f"R={rid}：评价日期缺失或不可解析，日期维度剔除")
        reason.iat[i] = "；".join(prob)

    for i in range(len(work)):
        if not keep.iat[i]:
            issues.append({"row": i + 2, "field": "行", "reason": reason.iat[i]})

    clean = work[keep].copy()
    report = {"total": total, "valid": int(keep.sum()),
              "excluded": int((~keep).sum()), "duplicates_removed": dup_removed,
              "issues": issues, "warnings": warnings}
    return clean, report


def load_builtin(name: str) -> pd.DataFrame:
    """加载仓库自带的模拟数据（name='products' 或 'reviews'）。"""
    base = Path(__file__).resolve().parent.parent / "data"
    return load_csv(base / f"{name}.csv")
