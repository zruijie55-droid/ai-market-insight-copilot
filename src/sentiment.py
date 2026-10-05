"""中文情感词典（规则版，零依赖，VADER 风格的透明实现）。

设计说明：
- VADER 是英语词典情感工具，对中文几乎无效；本模块用一份**可解释的中文正负向
  词表**实现等价的"词典情感"，契合本项目"透明、可审计、不调用大模型"的基线原则。
- 评分 = 正向词计数 − 负向词计数；>0 判为正向，<0 为负向，否则中性。
- 该方法是参考项目 shrutisurya108/Amazon-Review-Intelligence 中
  "VADER 词典情感 + 主题×情感热力图定位投诉热点" 方法论的中文适配版，
  但为原创实现（原仓库英文模型不可直接迁移到中文）。
- 当配置了 LLM API Key 时，src/llm.py 可提供更细的情感判断；本模块始终作为
  无 Key 兜底的确定性基线。
"""
from __future__ import annotations

# 正向词（出现即加分）
POSITIVE_WORDS = [
    "好用", "好使", "不错", "喜欢", "满意", "方便", "轻便", "便携", "小巧", "轻巧",
    "快充", "充电快", "充得快", "回血快", "耐用", "续航久", "续航长", "用得久",
    "实标", "不虚标", "扎实", "放心", "安全", "安全感", "靠谱", "稳定", "质量好",
    "划算", "性价比", "值", "实惠", "便宜", "好看", "漂亮", "美观", "颜值高",
    "给力", "强", "稳", "顶", "大容量", "容量大", "温控好", "不烫", "不发热",
    "推荐", "惊喜", "超值", "完美", "优秀", "优秀", "赞", "棒",
]

# 负向词（出现即减分）
NEGATIVE_WORDS = [
    "差", "坏", "太重", "很重", "偏重", "沉重", "压手", "沉甸甸", "坠", "重了",
    "慢", "充电慢", "充不进", "充不进去", "接触不良", "发热", "发烫", "烫手",
    "高温", "过热", "鼓包", "起火", "自燃", "爆炸", "危险", "隐患", "不安全",
    "虚标", "缩水", "不够用", "不耐用", "掉电", "续航短", "电量虚", "容量缩水",
    "贵", "不值", "不划算", "溢价", "肉疼", "丑", "老气", "不好看", "没质感",
    "问题", "故障", "担心", "担忧", "害怕", "失望", "后悔", "吐槽", "坑", "垃圾",
    "难用", "一般", "普通", "鸡肋", "烦", "麻烦", "漏液", "充不上",
]


def label(text: str) -> str:
    """返回 'positive' | 'negative' | 'neutral'。"""
    if not isinstance(text, str) or not text.strip():
        return "neutral"
    score = 0
    for w in POSITIVE_WORDS:
        if w in text:
            score += 1
    for w in NEGATIVE_WORDS:
        if w in text:
            score -= 1
    if score > 0:
        return "positive"
    if score < 0:
        return "negative"
    return "neutral"


def score(text: str) -> int:
    """返回情感净分（正词数 − 负词数），便于调试与排序。"""
    if not isinstance(text, str) or not text.strip():
        return 0
    s = 0
    for w in POSITIVE_WORDS:
        if w in text:
            s += 1
    for w in NEGATIVE_WORDS:
        if w in text:
            s -= 1
    return s
