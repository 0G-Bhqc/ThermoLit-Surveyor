# 评测(evaluation)

金标评测集是本项目可靠性的度量基础:**任何抽取/审计改动,都必须能回答"金标 F1 变好还是变坏"**。

## 金标集格式(`golden/*.jsonl`)

每行一条 JSON:

```json
{
  "id": "bi2te3-nw-001",
  "profile": "thermoelectric",
  "excerpt": "论文原文段落(通常为摘要或输运性质章节)",
  "source": {"title": "示例条目(合成数据,仅演示格式)", "doi": "10.0000/example", "synthetic": true},
  "expected": {
    "material_system": "Bi2Te3",
    "values": {
      "seebeck_coefficient": {"text": "-180 uV/K", "si": -1.8e-4},
      "electrical_conductivity": {"text": "1200 S/cm", "si": 120000.0},
      "thermal_conductivity": {"text": "1.3 W/mK", "si": 1.3},
      "zT_value": {"text": "0.9 @ 350 K", "si": 0.9}
    }
  }
}
```

要点:
- `expected.values.*.si` 为 **SI 单位下的真值**,由人工从原文核对;
- 目前纳入数值评测的仅限**审计引擎已支持 SI 解析的四个字段**:
  `seebeck_coefficient` / `electrical_conductivity` / `thermal_conductivity` / `zT_value`;
  `carrier_concentration`、`mobility` 虽会抽取但尚未做数值审计(M1 扩展解析器后纳入);
- `expected` 中未出现的字段表示"原文确实没有",用于考核"不编造"(LLM 输出该字段应为 null);
- 目前 `golden/thermoelectric_sample.jsonl` 为**格式演示用的合成样例**,真实金标集
  (20~50 篇热电文献)是 ROADMAP M1 的首要任务——从真实论文原文构建,禁止合成。

## 运行评测

```bash
# 校验金标集格式(无需 API key)
python eval/evaluate.py --gold eval/golden/thermoelectric_sample.jsonl --validate

# 完整评测(需要 DEEPSEEK_API_KEY;对每条 excerpt 跑真实抽取 + 确定性解析,与真值比对)
python eval/evaluate.py --gold eval/golden/thermoelectric_sample.jsonl
```

## 真实模型端到端烟雾测试(real_model_smoke.py)

无需 Sciverse token(检索端用固定语料替身),验证 提示词→LLM→JSON 解析→物理审计→
假说归一→实验方案→报告 全链路:

```bash
# 回放模式(离线可跑):eval/replay_fixtures/ 是一份"金标准示例",
# 展示每个 LLM 环节应当输出什么质量的内容
python eval/real_model_smoke.py

# 真实 LLM 模式:.env 配好任意 OpenAI 兼容端点后(DEEPSEEK_BASE_URL/MODEL/API_KEY)
python eval/real_model_smoke.py --live
```

产物写入 `eval/results/real_model_smoke/`:完整状态 JSON(记录+审计+假说+方案+指标)、
`report.md`、`audit_table.md`。闭环最后一环用 `thermolit --verify` 完成:把"实验测量值"
(SI)对着 smoke 输出的 hypotheses 回验,得到 supported / refuted / inconclusive 与缺口回流。

## 指标

| 指标 | 含义 | 目标 |
|------|------|------|
| 字段召回率 | 真值字段中被正确抽取出 SI 值的比例 | ≥ 0.90 |
| 数值相对误差中位数 | 抽取值 vs 真值(SI 单位)的中位相对误差 | ≤ 5% |
| 编造率 | 原文没有却抽取出值的字段比例 | = 0 |
| 审计一致率 | 对真值记录,物理引擎 flags 的误报率 | ≤ 10% |

指标随每次运行写入 `eval/results/<date>_<gold>.json`,供 CI 与 ROADMAP 进度追踪。
