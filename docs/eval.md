# 评测体系

金标评测是本项目可靠性的度量基础:**任何抽取/审计改动,都必须能回答"金标指标变好还是变坏"**。

## 金标集(`eval/golden/*.jsonl`)

每行一条 JSON,核心字段:

```json
{
  "id": "bi2te3-nw-001",
  "profile": "thermoelectric",
  "excerpt": "论文原文段落",
  "expected": {
    "material_system": "Bi2Te3",
    "values": {
      "seebeck_coefficient": {"text": "-180 uV/K", "si": -0.00018}
    }
  }
}
```

- `si` 为人工从原文核对的 SI 真值;
- `expected` 未列出的字段表示"原文确实没有",用于考核**编造率**;
- 当前纳入数值评测的四个字段:`seebeck_coefficient` / `electrical_conductivity` /
  `thermal_conductivity` / `zT_value`(审计引擎已支持 SI 解析的范围)。

## 运行

```bash
python eval/evaluate.py --gold eval/golden/thermoelectric_sample.jsonl --validate  # 仅校验格式
python eval/evaluate.py --gold eval/golden/thermoelectric_sample.jsonl             # 完整评测(需 LLM key)
```

## 指标与目标

| 指标 | 含义 | 目标 |
|------|------|------|
| 字段召回率 | 真值字段被正确抽取出 SI 值的比例 | ≥ 0.90 |
| 数值相对误差中位数 | 抽取值 vs 真值(SI)的中位相对误差 | ≤ 5% |
| 编造率 | 原文没有却解析出数值的比例 | = 0 |

## 真实模型端到端烟雾测试

```bash
python eval/real_model_smoke.py          # 回放模式(离线,replay_fixtures 为金标准示例)
python eval/real_model_smoke.py --live   # 真实 LLM(.env 任一可用端点)
```

固定语料替身检索端,验证 提示词 → LLM → JSON 解析 → 物理审计 → 假说归一 → 实验方案 →
报告 全链路;产物写入 `eval/results/real_model_smoke/`。闭环最后一环:
`thermolit --verify` 把"实验测量值"对假说做程序化回验。
