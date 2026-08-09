# ThermoLit-Surveyor: Literature Survey Agent for Materials Science

**English** | [中文文档](README_ZH.md)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-v1.2.10-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Sciverse API](https://img.shields.io/badge/Sciverse_API-v0.13.1-blueviolet.svg)](https://sciverse.opendatalab.com)

**ThermoLit-Surveyor** is a 2-Pass iterative, physics-constrained Literature Survey Agent designed for materials science research. Built on **LangGraph v1.2.10**, **Sciverse API v0.13.1 (MCP/Skill)**, and **DeepSeek LLM**, it automatically retrieves multi-hop literature, extracts structured domain entities, decouples transport properties via physical models, identifies physics-level Research Gaps, and generates audit-traceable hypothesis reports.

---

## 🌟 Key Architecture & Highlights

1. **Physics-Constrained Transport Decoupling Engine**:
   - Integrates the **Wiedemann-Franz Law** ($\kappa_e = L_0 \sigma T$) and the **Debye-Callaway Phonon Scattering Model** ($\tau_C^{-1} = \tau_U^{-1} + \tau_D^{-1} + \tau_B^{-1}$).
   - Automatically determines whether a reported high $zT$ value stems purely from electrical conductivity degradation or true lattice thermal conductivity reduction, bypassing superficial word-matching.

2. **2-Pass Gap-Driven Dynamic Multi-Hop Search**:
   - **Pass 1 (Broad Retrieval)**: Executes semantic retrieval across 25M+ full-text passage chunks via Sciverse API.
   - **Gap Reasoning**: LLM detects missing parameter voids (e.g., missing Seebeck coefficient $S$ or carrier mobility $\mu$).
   - **Pass 2 (Targeted Down-Drill Search)**: Dynamically generates targeted queries to fetch missing evidence and complete the knowledge graph.

3. **Three-Tier Audit Evidence Chain & Falsifiable Hypotheses**:
   - Classifies outputs into *Literature Facts* (mapped directly to DOIs), *Cross-Literature Inferences*, and *Falsifiable Hypotheses (H1~H5)* with strict quantitative thresholds and validation protocols.

---

## 📁 Repository Structure

```
├── config.py                           # Environment configuration & physical constants
├── sciverse_adapter.py                 # Sciverse API MCP / Skill adapter
├── prototype_multihop_deepresearch.py  # LangGraph 2-Pass state graph workflow
├── run_survey.py                       # CLI entry point for running literature surveys
├── test_agent.py                       # Automated test suite & data structure auditor
├── requirements.txt                    # Dependency lockfile
├── .env.example                        # Environment variables template
├── README.md                           # English main documentation
├── README_ZH.md                        # Chinese documentation
└── LICENSE                             # Apache-2.0 open-source license
```

---

## 🚀 Quickstart Guide

### 1. Installation

Ensure Python 3.11+ is installed, then clone the repository and install dependencies:

```bash
git clone https://github.com/0G-Bhqc/ThermoLit-Surveyor.git
cd ThermoLit-Surveyor
pip install -r requirements.txt
```

### 2. Environment Credentials Setup

Copy `.env.example` to `.env` or export environment variables directly:

```bash
# On Linux/macOS
export SCIVERSE_TOKEN="your_sciverse_token_here"
export DEEPSEEK_API_KEY="your_deepseek_api_key_here"

# On Windows (PowerShell)
$env:SCIVERSE_TOKEN="your_sciverse_token_here"
$env:DEEPSEEK_API_KEY="your_deepseek_api_key_here"
```

> **Note**: Obtain your Sciverse Token from [sciverse.opendatalab.com](https://sciverse.opendatalab.com) and DeepSeek API Key from [platform.deepseek.com](https://platform.deepseek.com).

### 3. Run Literature Survey Agent

Execute the default survey pipeline for $Bi_2Te_3$ thermoelectrics:

```bash
python run_survey.py
```

Run a custom material domain query:

```bash
python run_survey.py --query "PbTe thermoelectric lattice thermal conductivity phonon scattering" --output_report "pbte_survey_report.md"
```

---

## 🧪 Running Unit Tests

To run the automated integration test suite:

```bash
python test_agent.py
```

---

## 📜 License

This project is licensed under the [Apache-2.0 License](LICENSE).
