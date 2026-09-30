# 贡献指南

感谢关注 ThermoLit-Surveyor!本项目的质量门是:**离线测试全绿 + 金标指标不回退**。

## 开发环境

```bash
git clone https://github.com/0G-Bhqc/ThermoLit-Surveyor.git
cd ThermoLit-Surveyor

# Linux / macOS(路径纯 ASCII 时)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Windows 注意:仓库路径包含中文等非 ASCII 字符时,-e 安装会因 .pth 编码问题失败,
# 请使用常规安装: pip install ".[dev]" ,或设置环境变量 PYTHONUTF8=1 后再用 -e。

python -m unittest discover -s tests -v   # 全部测试,无需任何 API key
ruff check src tests eval                 # 代码风格
```

配置真实密钥(可选,仅在线集成测试与完整评测需要):

```bash
cp .env.example .env   # 填入 SCIVERSE_TOKEN / DEEPSEEK_API_KEY
```

## 项目结构与约定

```
src/thermolit/          # 核心包
  ├── config.py         # 配置(env 加载、调优项)
  ├── json_utils.py     # LLM JSON 提取 + 重试
  ├── physics.py        # 热电物理引擎(单位解析、WF 解耦、zT 校验)
  ├── adapter.py        # Sciverse 检索适配
  ├── graph.py          # LangGraph 编排(领域无关)
  └── profiles/         # 领域插件(DomainProfile)
tests/                  # 离线测试(必须不需要 API key 就能跑)
eval/                   # 金标评测
```

三条硬约定:

1. **数值只来自代码,不来自 LLM**。任何进入报告的派生物理量,必须在 profile 的
   `audit_record`(确定性函数)中计算并经过单元测试;LLM 只组织与解释。
2. **新功能必须带离线测试**。涉及 LLM 的逻辑用 monkeypatch 假 LLM 测编排与解析,
   不依赖网络与密钥(CI 无密钥环境必须全绿)。
3. **影响抽取/审计的改动必须跑金标评测**(`eval/evaluate.py`),并在 PR 中附指标对比。

## 如何新增一个领域 profile

这是本项目最重要的贡献方向(见 ROADMAP M3)。步骤:

1. 在 `src/thermolit/profiles/` 新建 `<domain>.py`,构造一个 `DomainProfile`:
   - `extraction_schema_prompt`:该领域需要抽取哪些参数、单位怎么写;
   - `audit_record`:把文本值解析成 SI 单位并计算领域派生量与异常标记(纯函数);
   - `build_table_md`:渲染该领域的《Physics Audit Table》;
   - `gap_query_hints`:缺失参数 → 定向检索提示;
   - `build_synthesis_prompt`:领域报告指令。
2. 在 `tests/` 为 `audit_record` 写数值用例(找一个已知答案的物理关系);
3. 在 `cli.py` 的 `PROFILES` 注册;在 `eval/golden/` 加格式样例。

## 提交

- 分支:`feat/xxx`、`fix/xxx`;
- 提交信息用祈使句,一次提交一个主题;
- PR 必须通过 CI(离线测试 + ruff);涉及物理引擎的 PR 请在描述中给出
  一个"改前 vs 改后"的审计表样例。
