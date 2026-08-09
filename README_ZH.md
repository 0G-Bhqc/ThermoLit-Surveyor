# ThermoLit-Surveyor: 材料科学文献驱动的科学发现调研智能体

[English Version](README.md) | **中文文档**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-v1.2.10-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Sciverse API](https://img.shields.io/badge/Sciverse_API-v0.13.1-blueviolet.svg)](https://sciverse.opendatalab.com)

**ThermoLit-Surveyor** 是一个针对材料科学（特别是热电材料领域）设计的 2-Pass 动态多跳、物理约束文献调研智能体。系统基于 **LangGraph v1.2.10** 编排工作流，联动 **Sciverse API v0.13.1 (MCP/Skill)** 与 **DeepSeek 大语言模型**，实现自主文献检索、实体抽取、输运参数物理解耦、Research Gap 识别与可证伪假说自动生成。

---

## 🌟 核心架构与技术亮点

1. **物理约束驱动的参数解耦引擎**：
   - 引入 **Wiedemann-Franz 定律**（$\kappa_e = L_0 \sigma T$）与 **Debye-Callaway 声子散射模型**（$\tau_C^{-1} = \tau_U^{-1} + \tau_D^{-1} + \tau_B^{-1}$）。
   - 自动判定文献报道的高 $zT$ 是否仅由电导率下降导致，克服纯词频匹配无法识别物理实质的局限。

2. **2-Pass 缺口驱动的动态多跳搜索机制**：
   - **Pass 1 (广域检索)**：通过 Sciverse API 检索 2800万+ 全文片段。
   - **缺口识别**：LLM 识别参数真空（如缺少 Seebeck 系数 $S$ 或迁移率 $\mu$）。
   - **Pass 2 (定向下钻检索)**：自适应生成 Targeted Queries 进行二次补全与闭环融合。

3. **三层可审计证据链与可证伪假说生成**：
   - 对产出进行分级标注（文献事实精准映射原文 DOI，跨文献推论标记参与文献，待验证假说 H1~H5 强制包含定量判据与验证实验）。

---

## 📁 项目目录结构

```
├── config.py                           # 环境变量、模型配置与物理常数
├── sciverse_adapter.py                 # Sciverse API MCP / Skill 检索适配器
├── prototype_multihop_deepresearch.py  # LangGraph 2-Pass 状态图工作流
├── run_survey.py                       # 命令行一键调研入口
├── test_agent.py                       # 自动化单元测试与数据结构审计
├── requirements.txt                    # 依赖配置文件
├── .env.example                        # 环境变量配置模版
├── README.md                           # 英文主 README
├── README_ZH.md                        # 中文 README 文档
└── LICENSE                             # Apache-2.0 开源协议
```

---

## 🚀 快速上手

### 1. 安装环境

确保安装了 Python 3.11+，拉取仓库并安装依赖：

```bash
git clone https://github.com/0G-Bhqc/ThermoLit-Surveyor.git
cd ThermoLit-Surveyor
pip install -r requirements.txt
```

### 2. 环境变量与秘钥配置

复制 `.env.example` 为 `.env`，或直接设置环境变量：

```bash
# Linux/macOS
export SCIVERSE_TOKEN="您的_sciverse_token"
export DEEPSEEK_API_KEY="您的_deepseek_api_key"

# Windows (PowerShell)
$env:SCIVERSE_TOKEN="您的_sciverse_token"
$env:DEEPSEEK_API_KEY="您的_deepseek_api_key"
```

> **提示**：注册 [Sciverse API](https://sciverse.opendatalab.com) 获取 Token；在 [DeepSeek Platform](https://platform.deepseek.com) 获取 API Key。

### 3. 运行文献调研 Agent

运行默认的 $Bi_2Te_3$ 热电材料输运解耦与 Gap 调研工作流：

```bash
python run_survey.py
```

自定义材料主题调研：

```bash
python run_survey.py --query "PbTe thermoelectric lattice thermal conductivity phonon scattering" --output_report "pbte_survey_report.md"
```

---

## 🧪 单元测试

运行集成测试套件验证接口与数据结构：

```bash
python test_agent.py
```

---

## 📜 开源协议

本项目采用 [Apache-2.0 License](LICENSE) 开源协议。
