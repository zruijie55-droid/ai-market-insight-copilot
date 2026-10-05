# 第三方组件与开源合规声明（THIRD PARTY NOTICES）

本文件说明本项目对外部代码/方法论的引用方式与许可证状态，以满足「保留开源许可证要求的
必要声明」与「明确原有功能与新增功能」的交付要求。

---

## 1. 参考项目（仅借鉴方法论，**未复制任何代码**）

**参考仓库**：[shrutisurya108/Amazon-Review-Intelligence](https://github.com/shrutisurya108/Amazon-Review-Intelligence)
（一个基于 21,737 条 Amazon 电子评论的端到端 NLP 项目，使用 VADER + DistilBERT 做情感、
LDA 做主题、主题×情感热力图定位投诉热点。）

**合规核查结论（已实测）**：
- 经 GitHub API 核验（`GET /repos/.../license`），该仓库**未包含任何 LICENSE 文件**
  （返回 `404 Not Found`）。
- 依据开源惯例，**无 LICENSE = 保留所有权利（all rights reserved）**，他人无权复制、
  修改或再分发其源代码。

**本项目据此采取的做法**：
- **未复制、未再分发该仓库的任何源代码**；
- 仅**借鉴其分析方法论思路**，并针对本项目场景（**中文移动电源用户评价**）**自主实现**：
  - 其「VADER 词典情感」→ 本项目 `src/sentiment.py` 的**中文情感词典**（VADER 为英语词典，
    对中文无效，故重写为中文正负向词表，等价实现「词典情感」基线）；
  - 其「LDA 主题建模」→ 本项目 `src/insights.py` 的**透明关键词主题规则**（LDA 在英语语料
    训练，不可直接迁移中文，且本项目强调「可解释、可审计」故选用透明规则而非黑盒模型）；
  - 其「主题 × 情感热力图定位投诉热点」→ 本项目 `src/insights.py` 的 `theme_sentiment`
    矩阵与 `app.py` 中的热力图（方法同构，代码为本项目原创）。
- 在 README「开源与引用」一节与本文档中**明确标注参考来源与方法论**，不冒用其成果。

---

## 2. 本项目直接使用的开源依赖（运行时）

| 依赖 | 用途 | 许可证 |
|------|------|--------|
| [Python](https://www.python.org) | 运行环境 | PSF License |
| [pandas](https://pandas.pydata.org/) | 数据处理 | BSD-3-Clause |
| [NumPy](https://numpy.org/) | 数值计算 | BSD-3-Clause |
| [Streamlit](https://streamlit.io/) | Web 应用框架 | Apache-2.0 |
| [Plotly](https://plotly.com/python/) | 可视化 | MIT |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 读取 .env 环境变量 | BSD-3-Clause |
| [openpyxl](https://openpyxl.readthedocs.io/) | 读取 Excel(.xlsx) | MIT |
| [openai](https://github.com/openai/openai-python) | 可选：大模型增强（仅启用时） | Apache-2.0 |

上述依赖各自遵循其开源许可证。本项目以 MIT 许可证发布（见 `LICENSE` 文件）。

---

## 3. 原有功能 vs 本次新增功能（变更说明）

**原有（规则版 V1，已交付）**
- 数据校验（不静默丢行、记录排除原因、样本量展示）
- 竞品与价格带分析（价格带可配、品牌价格对比、参数×价格散点）
- 透明关键词主题洞察 + 原文证据回溯
- 基于规则的可解释机会假设 + Markdown/HTML/CSV 报告

**本次新增（V1.1）**
- 模块1：支持 **Excel(.xlsx)** 上传；**字段识别**（常见中/英文表头别名自动映射）；去重计数
- 模块2：**产品参数逐项对比**；品牌维度属性对比（均价/容量/功率/重量）
- 模块3：**中文情感词典**情感标注；**主题 × 情感热力图**与**痛点排序**；多情感筛选看原文证据
- 大模型 API（可选）：通过**环境变量**配置 Key，侧边栏开关启用，增强情感/主题/假设描述，
  所有模型输出均标注为**待验证**
- 合规：新增 `LICENSE`（MIT）、本文件、更新 README

---

## 4. 数据合规
- 全部演示数据为**模拟生成**（source=synthetic），不含任何真实企业数据、用户隐私或
  未授权抓取内容。
- API Key 仅从环境变量读取（`.env`，已被 `.gitignore` 排除），**不写入源代码、不提交仓库**。
