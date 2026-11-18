# fin-llm-badcase-eval · 中文金融问答 Badcase 评测

> 状态：评测进行中（题库与评分细则已定稿，模型回答采集中）。结果与报告完成后更新本页。

## 这是什么

一个小而严谨的中文金融问答评测集，对比 DeepSeek、豆包、千问、Kimi 四个国产大模型，重点不在给模型排名，而在**归纳错误类型、定位根因、提出数据与评测层面的改进方向**。

- **30 道题，7 类**：计算与定价、宏观传导与因果、财报与会计陷阱、交易风控与仓位、合规与边界、时效与幻觉、量化研究与计量
- **4 类提问人群**：从业者、量化研究者、学生、普通投资者
- **5 维评分**：结论正确性、推理过程、风险与合规、不确定性表达、可用性（各 0–2 分）
- **人工复核**：初评后由作者逐条复核，LLM 自动打分仅作对照

## 仓库结构

```
data/
  questions.jsonl        题库（题目、标准答案、评分要点、容差、可接受等价回答、出处、陷阱）
  questions_review.md    由 jsonl 自动生成的审阅版
  rubric.md              评分细则
  collection_plan.md     采集方案与统一条件
scripts/
  collect.py             通过官方 API 采集回答（含思考过程）
  models_config.json     各模型接口配置
  render_review.py       生成审阅版
responses/               模型原始回答（采集后）
scores/                  评分结果（打分后）
figures/                 图表（分析后）
```

## 如何复现

见 [RUN.md](RUN.md)。API Key 只放在本地 `.env`，不提交到仓库。

## 局限

样本量小（30 题）、单次采集、人工打分有主观性；结果只代表采集当日的模型版本与 API 条件，不用于给模型排名。

---

*English summary will be added with the final report.*
