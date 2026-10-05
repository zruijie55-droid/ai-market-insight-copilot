"""生成 V1 演示用的模拟数据（移动电源 / power bank）。

设计要点：
- 固定随机种子，数据可复现；
- 所有数据均标注 source=synthetic，不代表真实市场；
- 评价文本围绕透明规则主题（便携/重量、容量/续航、充电速度、发热、安全感、价格、外观）
  构造，含正负差异，便于演示 F3 主题洞察；
- 内置少量「缺失评分 / 缺失日期 / 空文本」行，用于演示 F1 的友好提示；
- 另生成 sample_broken_*.csv，用于手动验证数据质量校验（F1）。

运行：python data/generate_mock.py
"""
from __future__ import annotations
import csv
import random
from pathlib import Path

SEED = 42
OUT = Path(__file__).resolve().parent

BRANDS = [
    "安克", "小米", "罗马仕", "倍思", "绿联", "品胜", "羽博",
    "京东京造", "爱国者", "飞利浦", "紫米", "摩米士", "锐舞", "酷态科",
]

# 价格带意图：制造低/中/高三档，便于价格带分析有内容
PRICE_TIERS = [
    (79, 99), (109, 149), (159, 199), (219, 269), (299, 369), (399, 499),
]

# 主题关键词库（与 src/insights.py 中 THEMES 对应，保证可复现演示）
THEME_TEXTS = {
    "便携/重量": {
        "pos": ["很轻便，放包里完全没感觉", "小巧便携，出差带着方便", "比想象中轻，携带无压力",
                "体积很小巧，单手可握", "轻巧不占地方"],
        "neg": ["太重了，放口袋坠得慌", "体积偏大，携带不太方便", "拿在手里沉甸甸的",
                "比旧款重了不少", "偏重，通勤不太友好"],
    },
    "容量/续航": {
        "pos": ["20000mAh 容量很顶，出差两天够用", "续航耐用，充满手机三次还有余",
                "标称容量没虚标，电量很实", "容量大，长途旅行也不慌"],
        "neg": ["容量虚标严重，实际续航很短", "标 30000mAh 实际根本不够用", "电量掉得快，不耐用",
                "续航短，半天就要充一次", "容量缩水明显"],
    },
    "充电速度": {
        "pos": ["支持快充，回血很快", "充电速度很给力，半小时充一大半", "充得快，急用不耽误",
                "PD 快充体验很好"],
        "neg": ["充电慢，充了一晚上还没满", "不支持快充，充电速度一般", "充电口接触不良充不进",
                "充电特别慢，急死人"],
    },
    "发热": {
        "pos": ["工作时几乎不发热，温控不错", "温热但不烫，安全感强"],
        "neg": ["充电时发烫严重，烫手", "用一会儿就发热，有点担心", "高温报警过一次，吓人",
                "发热明显，外壳很烫"],
    },
    "安全感": {
        "pos": ["用料扎实，用着放心", "多重保护，安全感满满", "大品牌质量靠谱"],
        "neg": ["鼓包了，太危险", "担心起火自燃，不敢用了", "质量不稳定，安全隐患大",
                "做工一般，不太放心"],
    },
    "价格": {
        "pos": ["性价比很高，这个价格值", "便宜好用，学生党友好", "价位合理，划算"],
        "neg": ["价格偏贵，不太值", "同样配置别家更便宜", "溢价太高，不划算",
                "这个价钱有点肉疼"],
    },
    "外观": {
        "pos": ["颜值高，外观好看", "设计简洁漂亮，喜欢", "造型美观，摆着也好看"],
        "neg": ["外观一般，颜值普通", "设计老气，不太好看", "造型丑，没质感"],
    },
}

THEME_KEYS = list(THEME_TEXTS.keys())


def make_products(n: int = 40) -> list[dict]:
    rng = random.Random(SEED)
    rows = []
    for i in range(1, n + 1):
        brand = rng.choice(BRANDS)
        lo, hi = rng.choice(PRICE_TIERS)
        price = round(rng.uniform(lo, hi), 1)
        capacity = rng.choice([5000, 10000, 15000, 20000, 25000, 30000])
        power = rng.choice([18, 20, 22.5, 30, 45, 65, 100, 140])
        # 约 12% 概率缺失重量，演示参数缺失提示
        weight = round(rng.uniform(180, 620), 1) if rng.random() > 0.12 else ""
        rows.append({
            "product_id": f"P{i:03d}",
            "brand": brand,
            "product_name": f"{brand} {capacity}mAh {int(power)}W 移动电源",
            "price": price,
            "capacity_mah": capacity,
            "power_w": power,
            "weight_g": weight,
            "source": "synthetic",
        })
    return rows


def make_reviews(products: list[dict], total: int = 420) -> list[dict]:
    rng = random.Random(SEED + 1)
    rows = []
    for i in range(1, total + 1):
        prod = rng.choice(products)
        # 评分分布：多数好，少数差，制造低分主题信号
        r = rng.random()
        if r < 0.12:
            rating = rng.randint(1, 2)      # 低分
        elif r < 0.22:
            rating = 3                       # 中性
        else:
            rating = rng.randint(4, 5)       # 高分
        # 选 1~2 个主题
        n_theme = rng.choice([1, 1, 2])
        themes = rng.sample(THEME_KEYS, n_theme)
        parts = []
        for t in themes:
            pool = THEME_TEXTS[t]["pos"] if rating >= 4 else THEME_TEXTS[t]["neg"]
            parts.append(rng.choice(pool))
        text = "，".join(parts) + "。"
        # 日期：集中在近一年
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        date = f"2025-{month:02d}-{day:02d}"
        rows.append({
            "review_id": f"R{i:04d}",
            "product_id": prod["product_id"],
            "rating": rating,
            "review_text": text,
            "review_date": date,
            "source": "synthetic",
        })
    # 注入少量「异常但合法」行用于演示提示（不破坏整体可用性）
    # 1) 空文本（应被文本洞察排除）
    rows.append({"review_id": "R9001", "product_id": "P001", "rating": 5,
                 "review_text": "", "review_date": "2025-03-10", "source": "synthetic"})
    # 2) 缺失评分（仍可参与文本洞察，但评分分组剔除）
    rows.append({"review_id": "R9002", "product_id": "P002", "rating": "",
                 "review_text": "整体还行，就是有点重。", "review_date": "2025-04-01", "source": "synthetic"})
    # 3) 缺失日期（参与分析，日期维度剔除）
    rows.append({"review_id": "R9003", "product_id": "P003", "rating": 4,
                 "review_text": "容量大续航耐用。", "review_date": "", "source": "synthetic"})
    return rows


def make_broken_products() -> list[dict]:
    """用于手动验证 F1 校验的损坏样例。"""
    return [
        {"product_id": "P001", "brand": "安克", "product_name": "安克 20000mAh 移动电源",
         "price": 159, "capacity_mah": 20000, "power_w": 22.5, "weight_g": 350, "source": "synthetic"},
        {"product_id": "P001", "brand": "安克", "product_name": "重复ID样例",
         "price": 159, "capacity_mah": 20000, "power_w": 22.5, "weight_g": 350, "source": "synthetic"},  # 重复 ID
        {"product_id": "", "brand": "无ID", "product_name": "缺 product_id",
         "price": 99, "capacity_mah": 10000, "power_w": 18, "weight_g": 200, "source": "synthetic"},    # 空 ID
        {"product_id": "P002", "brand": "小米", "product_name": "负价格样例",
         "price": -50, "capacity_mah": 10000, "power_w": 18, "weight_g": 200, "source": "synthetic"},   # 负价
        {"product_id": "P003", "brand": "绿联", "product_name": "容量无效",
         "price": 129, "capacity_mah": -5000, "power_w": 20, "weight_g": 210, "source": "synthetic"},  # 负容量
        {"product_id": "P004", "brand": "倍思", "product_name": "功率缺失",
         "price": 139, "capacity_mah": 15000, "power_w": "", "weight_g": 240, "source": "synthetic"},  # 功率空
        # 缺列行（无 product_name）
        {"product_id": "P005", "brand": "品胜", "price": 119,
         "capacity_mah": 12000, "power_w": 20, "weight_g": 230, "source": "synthetic"},
    ]


def make_broken_reviews() -> list[dict]:
    return [
        {"review_id": "R0001", "product_id": "P001", "rating": 5,
         "review_text": "很好用。", "review_date": "2025-01-01", "source": "synthetic"},
        {"review_id": "R0001", "product_id": "P001", "rating": 4,
         "review_text": "重复 review_id。", "review_date": "2025-01-02", "source": "synthetic"},  # 重复 ID
        {"review_id": "R0002", "product_id": "P999", "rating": 3,
         "review_text": "商品不存在。", "review_date": "2025-01-03", "source": "synthetic"},        # 外键不匹配
        {"review_id": "R0003", "product_id": "P001", "rating": 9,
         "review_text": "评分超范围。", "review_date": "2025-01-04", "source": "synthetic"},        # 评分越界
        {"review_id": "R0004", "product_id": "P001", "rating": 2,
         "review_text": "", "review_date": "2025-01-05", "source": "synthetic"},                  # 空评价
        {"review_id": "R0005", "product_id": "P002", "rating": "好",
         "review_text": "评分非数字。", "review_date": "2025-01-06", "source": "synthetic"},        # 评分非数字
    ]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  wrote {path}  ({len(rows)} rows)")


def main():
    products = make_products(40)
    reviews = make_reviews(products, 420)
    _write_csv(OUT / "products.csv",
               ["product_id", "brand", "product_name", "price",
                "capacity_mah", "power_w", "weight_g", "source"], products)
    _write_csv(OUT / "reviews.csv",
               ["review_id", "product_id", "rating", "review_text",
                "review_date", "source"], reviews)
    _write_csv(OUT / "sample_broken_products.csv",
               ["product_id", "brand", "product_name", "price",
                "capacity_mah", "power_w", "weight_g", "source"],
               make_broken_products())
    _write_csv(OUT / "sample_broken_reviews.csv",
               ["review_id", "product_id", "rating", "review_text",
                "review_date", "source"], make_broken_reviews())
    print("模拟数据生成完成（全部 source=synthetic，不代表真实市场）。")


if __name__ == "__main__":
    main()
