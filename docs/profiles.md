# 领域 Profile 开发

`DomainProfile` 把领域知识从编排中解耦——新增一个领域(超导、锂电、催化…)**零改动** `graph.py`。

## 一个 Profile 是什么

```python
from thermolit.profiles.base import DomainProfile

MY_PROFILE = DomainProfile(
    name="my-domain",
    description="审计什么物理量(一句话)",
    extraction_schema_prompt=...,      # 抽取 JSON schema 指令(含 evidence_sentences 要求)
    audit_record=my_audit_record,      # 记录 → 解析值 + 派生量 + flags + missing(纯函数!)
    build_table_md=my_table,           # 审计记录列表 → 《Physics Audit Table》
    gap_query_hints={...},             # 缺失参数 → 定向检索提示
    build_synthesis_prompt=...,        # 合成指令(报告必须以审计表为数值基准)
    build_hypothesis_prompt=...,       # 可选:研究闭环(假说)
    build_experiment_prompt=...,       # 可选:实验方案设计
)
```

## 三条硬规则

1. **数值只来自代码**:`audit_record` 必须是确定性纯函数,把文本解析为 SI 并计算派生量;
   LLM 只负责组织与解释。
2. **判据用规范变量**:假说判据与实验测量目标必须使用 `thermolit.hypothesis.CANONICAL_VARS`
   中的变量(S、σ、κ_l、zT、PF…),否则无法程序化回验。
3. **离线可测**:`audit_record` 的每个数值关系都要有单元测试;涉及 LLM 的编排逻辑用
   假 LLM/假适配器测试(tests/test_graph_offline.py 是模板)。

## 接入步骤

1. `src/thermolit/profiles/` 新建 `<domain>.py`,构造 `DomainProfile`;
2. `tests/` 为 `audit_record` 写数值用例(找已知答案的物理关系);
3. `cli.py` 的 `PROFILES` 注册;
4. `eval/golden/` 加该领域的金标格式样例;
5. 运行 `thermolit --profile <domain>` 验证全流程。

参考实现:`profiles/thermoelectric.py`(含 Wiedemann-Franz 解耦、zT 一致性、非晶下限筛查)。
