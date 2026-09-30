# ThermoLit-Surveyor: 物理约束的研究闭环智能体框架

[English Version](README.md) | **中文文档**

[![CI](https://github.com/0G-Bhqc/ThermoLit-Surveyor/actions/workflows/ci.yml/badge.svg)](https://github.com/0G-Bhqc/ThermoLit-Surveyor/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://www.python.org/)

**ThermoLit-Surveyor** 是一个覆盖**调研之后研究闭环**的"缺口驱动、物理约束"智能体框架:
文献调研 → 结构化可证伪假说 → 实验方案设计 → **实验结果程序化回验** → 生成新一轮缺口。
每个环节之间都有**确定性领域审计层**:数值由程序计算、可溯源到 DOI、可离线测试。
领域知识通过 `DomainProfile` 插件接入;首个 profile 为**热电输运**(Seebeck / σ / κ / zT)。

**为什么不同**:通用 DeepResearch 智能体止步于一份报告,且数值由 LLM 自由生成、无法审计。
ThermoLit-Surveyor:(1) 在代码中确定性地计算 `κ_e = L·σ·T`、`κ_l = κ_tot − κ_e`、
`zT_calc = S²σT/κ`,并把程序生成的《Physics Audit Table》作为合成的唯一数值基准;
(2) 把"H1~H5 假说"变成**结构化对象**(规范 SI 变量 + 数值阈值),程序可以直接回验;
(3) 闭环:实验完成后 `thermolit --verify` 逐条程序化判定假说,缺失变量自动回流为
下一轮调研的定向缺口。

---

## 🌟 核心架构与技术亮点

1. **确定性物理审计层(核心创新)**:
   - 带单位文本解析(µV/K、S/cm、mΩ·cm、mW/cmK、×10⁵ …)→ SI 值,纯函数、全单元测试;
   - Wiedemann-Franz 解耦与 zT 一致性**在代码中计算而非提示词口算**;
     自动标记 `κ_l < 0`、zT 偏差 > 30%、κ_l 低于非晶下限;
   - 报告必须以程序生成的《Physics Audit Table》为唯一数值真相。

2. **解析器驱动的缺口闭环(2-Pass 检索)**:
   - **Pass 1(广域)**:Sciverse API 检索 2500万+ 全文段落;
   - **缺口识别是数据驱动的**:缺失参数 = 单位解析失败/字段缺失的确定性产物,不是 LLM 自评;
   - **Pass 2(定向)**:由真实缺口列表生成补查查询,形成 抽取→解析→缺口→检索→再抽取 闭环。

3. **研究闭环:调研之后的环节(0.3.0 新增)**:
   - **结构化可证伪假说**:判据必须是 规范 SI 变量 + 数值阈值(+可选温度条件),
     由代码归一校验——幻觉变量、非数值阈值、无判据"假说"一律剔除;
   - **实验方案设计**:样品矩阵 + 每次测量的目标变量(规范变量)与温度区间,
     由代码校验测量目标与假说引用;
   - **确定性回验**:实验测得值(SI)→ 派生变量 → 逐判据程序判定
     supported / refuted / inconclusive;缺失变量回流为下一轮调研缺口。

4. **可插拔 DomainProfile 架构**:
   - 一个 profile = 抽取 schema + 审计引擎 + 审计表渲染 + 缺口提示 + 假说/实验指令 + 合成指令;
   - LangGraph 编排(`graph.py`)领域无关;新增领域(超导、锂电、催化)零改动编排层。

5. **可靠性是特性**:
   - 40+ 离线测试:整个智能体(图编排、假说、实验方案)可用假 LLM/假适配器端到端运行
     ——**无需任何 API key**,CI 友好;
   - 金标评测体系(字段召回率/数值误差/编造率),见 `eval/`;
   - 假说判定(supported/refuted/inconclusive)永远由代码给出,不由 LLM 自评。

---

## 📁 项目目录结构

```
├── src/thermolit/                      # 核心包
│   ├── config.py                       # 配置(python-dotenv 加载 .env)与调优项
│   ├── json_utils.py                   # 围栏感知 JSON 提取 + 重试
│   ├── schemas.py                      # Pydantic 抽取契约(校验失败回喂重试)
│   ├── physics.py                      # 热电物理引擎(单位解析、WF 解耦、zT 审计)
│   ├── hypothesis.py                   # 结构化可证伪假说 + 确定性回验引擎
│   ├── doi.py                          # DOI 注册库核验(doi.org handle API)
│   ├── adapter.py                      # Sciverse 检索适配(惰性客户端、重试、去重)
│   ├── graph.py                        # 领域无关的 LangGraph 编排(10 节点)
│   ├── export.py                       # Markdown 报告 → docx
│   ├── api.py                          # FastAPI 服务(POST /survey + GET /jobs)
│   ├── cli.py                          # `thermolit` CLI(--profile/--verify/--checkpoint/--export_docx)
│   └── profiles/                       # DomainProfile 领域插件
│       ├── base.py                     #   接口 + 通用行为
│       └── thermoelectric.py           #   首个 profile(热电输运研究闭环)
├── tests/                              # 离线测试套件(无需 API key)
├── eval/                               # 金标评测 + 真实模型烟雾测试(--live/--replay)
├── .github/workflows/ci.yml            # CI:ruff + 离线测试(py3.11/3.12 矩阵)
├── pyproject.toml                      # 打包 + 命令行入口 + extras(server/export/checkpoint)
├── Dockerfile                          # docker run 即起 FastAPI 服务
├── ROADMAP.md / CHANGELOG.md / CONTRIBUTING.md
├── run_survey.py / test_agent.py       # 薄兼容入口
└── .env.example                        # 凭证模板(自动加载 .env)
```

以 API 服务运行:

```bash
pip install ".[server]"
uvicorn thermolit.api:app --port 8000          # 或: docker build -t thermolit . && docker run -p 8000:8000 thermolit
curl -X POST localhost:8000/survey -H "content-type: application/json" -d '{"query": "PbTe zT decoupling"}'
```

---

## 🚀 快速上手

### 1. 安装

确保 Python 3.11+,克隆并安装:

```bash
git clone https://github.com/0G-Bhqc/ThermoLit-Surveyor.git
cd ThermoLit-Surveyor
pip install -e ".[dev]"    # Windows 路径含中文时改用: pip install ".[dev]"
python -m unittest discover -s tests -v   # 离线测试,无需 API key
```

### 2. 环境变量与秘钥配置

复制 `.env.example` 为 `.env`(python-dotenv 自动加载),或直接设置环境变量:

```bash
# Linux/macOS
export SCIVERSE_TOKEN="您的_sciverse_token"
export DEEPSEEK_API_KEY="您的_deepseek_api_key"

# Windows (PowerShell)
$env:SCIVERSE_TOKEN="您的_sciverse_token"
$env:DEEPSEEK_API_KEY="您的_deepseek_api_key"
```

> **提示**:注册 [Sciverse API](https://sciverse.opendatalab.com) 获取 Token;DeepSeek
> 或任意 OpenAI 兼容端点均可,通过 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` 切换。

### 3. 运行文献调研 Agent

运行默认的热电输运解耦与 Gap 调研工作流:

```bash
thermolit                                  # 等价: python run_survey.py
```

自定义调研主题:

```bash
thermolit --query "PbTe thermoelectric lattice thermal conductivity phonon scattering" \
          --output_report "pbte_survey_report.md"
```

作为 Python 库调用:

```python
from thermolit import run_agent, evaluate_hypotheses, THERMOELECTRIC_PROFILE

state = run_agent("PbTe thermoelectric zT decoupling", profile=THERMOELECTRIC_PROFILE)
print(state["audit_table_md"])      # 程序计算的审计表
print(state["hypotheses"])          # 结构化可证伪假说(SI 变量 + 阈值)
print(state["experiment_plan"])     # 实验方案,测量目标为规范变量
print(state["deep_gap_report"])     # 数值有据可查的调研报告

# 实验完成后:用测量值(SI)程序化回验
verdicts = evaluate_hypotheses(state["hypotheses"], {
    "S": -1.8e-4, "sigma": 1.2e5, "kappa": 1.3, "T_K": 350})
# -> [{"id": "H1", "status": "supported" | "refuted" | "inconclusive", ...}]
```

命令行回验模式(不执行调研):

```bash
thermolit --verify results.json      # results.json: {"measurements": {"S": ..., "sigma": ...}}
# 输出逐条假说判定 + 把缺失变量回流为下一轮调研的定向缺口
```

---

## 🆕 0.3.0 更新(调研之后:研究闭环)

- **`hypothesize` 节点**:审计表 → **结构化可证伪假说**——判据必须是规范 SI 变量 +
  数值阈值(+可选温度条件),`hypothesis.normalize_hypotheses` 确定性校验:
  幻觉变量、非数值阈值、无判据"假说"一律剔除;引用审计表外 DOI 自动打标。
- **`design_experiments` 节点**:假说 → 实验方案,确定性校验
  (测量目标必须是规范变量、假说引用必须存在)。
- **确定性回验**:`evaluate_hypotheses` 从测量 SI 值派生 PF / zT / κ 分量,
  逐判据代码判定,并把缺失变量经 `missing_to_gap_queries` 回流为下一轮调研缺口——闭环。
- CLI 新增 `thermolit --verify results.json` 回验模式;调研 JSON 输出新增
  `hypotheses` / `experiment_plan`(可直接作为回验输入)。工作流 8 → **10 节点**。

---

## 🆕 0.2.0 更新(物理约束真正落地)

- **确定性物理审计引擎 `physics.py`**:带单位文本解析 → SI → 在代码中真实计算
  Wiedemann-Franz 解耦(`κ_e = L·σ·T`,Lorenz 数随 |S| 自适应)、`κ_l = κ_tot − κ_e`、
  `zT_calc = S²σT/κ`;自动标记 `κ_l < 0`、zT 偏差 > 30%、κ_l 低于非晶下限;
  报告以程序生成的《Physics Audit Table》为唯一数值基准,LLM 不得改写数值。
- **DomainProfile 插件架构**:领域知识(抽取 schema、审计引擎、缺口提示、合成指令)
  与 LangGraph 编排解耦,新增领域零改动编排层;首个 profile:`thermoelectric`。
- **缺口驱动检索闭环**:参数缺口由"单位解析失败/字段缺失"数据驱动判定,
  定向补查由真实缺口生成,材料体系从抽取结果自动投票,移除 Bi2Te3 硬编码。
- **健壮性**:`.env` 自动加载、围栏感知 JSON 解析、错误记录与正常记录分离、
  Pass 1/2 论文去重、并行抽取、指数退避重试、CLI 新增 `--top_k/--followup/--log_level`。
- **开源工程化**:src 布局、hatchling 打包、`thermolit` 命令行入口、
  GitHub Actions CI(py3.11/3.12)、金标评测骨架、
  30 个测试(单元 + 离线端到端,无需任何 API key);详见 [ROADMAP.md](ROADMAP.md)。

工作流:pass1_search → pass1_extract → **pass1_audit** → query_refine → pass2_search → pass2_extract → **pass2_audit** → **hypothesize** → **design_experiments** → synthesize
(实验完成后 `thermolit --verify` 回验,闭环)

---

## 🧪 单元测试

单元与离线端到端测试无需 API key;配置 `SCIVERSE_TOKEN` 后自动追加真实 API 集成测试:

```bash
python -m unittest discover -s tests -v    # 等价: python test_agent.py
```

---

## 📜 开源协议

本项目采用 [Apache-2.0 License](LICENSE) 开源协议。
