# ThermoLit-Surveyor: Physics-Constrained Research-Loop Agent Framework

**English** | [中文文档](README_ZH.md)

[![CI](https://github.com/0G-Bhqc/ThermoLit-Surveyor/actions/workflows/ci.yml/badge.svg)](https://github.com/0G-Bhqc/ThermoLit-Surveyor/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://www.python.org/)

**ThermoLit-Surveyor** is a gap-driven, physics-constrained agent **framework covering the research loop after the survey**: literature survey → structured falsifiable hypotheses → experiment design → **deterministic verification of experimental results** → next-round gap targeting. Between every stage sits a **deterministic domain audit layer**: numbers are computed by code, traceable to a DOI, and testable offline. Domain knowledge is pluggable via `DomainProfile`; the first profile is **thermoelectric transport** (Seebeck / σ / κ / zT).

**Why it is different**: generic DeepResearch agents stop at a written report, and let the LLM freely generate its numbers — unauditable. ThermoLit-Surveyor (1) computes `κ_e = L·σ·T` (Wiedemann-Franz, Seebeck-adaptive Lorenz number), `κ_l = κ_tot − κ_e`, and `zT_calc = S²σT/κ` in deterministic code and injects this *Physics Audit Table* as the single numeric ground truth; (2) turns "H1–H5 hypotheses" into **structured objects** (canonical SI variables + numeric thresholds) that a program can verify; (3) closes the loop: after the lab runs, `thermolit --verify` programmatically judges each hypothesis and refluxes missing variables into the next survey's gap queries.

---

## 🌟 Key Architecture & Highlights

1. **Deterministic Physics Audit Layer** (the core innovation):
   - Parses unit-bearing text (µV/K, S/cm, mΩ·cm, mW/cmK, ×10⁵ …) into SI values — pure functions, fully unit-tested.
   - Computes Wiedemann-Franz decoupling and zT consistency **in code, not in the prompt**; flags `κ_l < 0`, zT mismatch > 30%, sub-amorphous `κ_l`.
   - The synthesized report must treat the programmatically generated *Physics Audit Table* as the single source of numeric truth.

2. **Parser-Driven Gap Loop (2-Pass retrieval)**:
   - **Pass 1 (broad)**: semantic retrieval over 25M+ full-text passages via Sciverse API.
   - **Gap detection is data-driven**: missing parameters = fields whose unit parsing failed, not an LLM's self-assessment.
   - **Pass 2 (targeted)**: follow-up queries generated from the real gap list, closing the extract → parse → gap → retrieve → re-extract loop.

3. **Pluggable DomainProfile architecture**:
   - One profile = extraction schema + audit engine + audit-table renderer + gap hints + synthesis directives.
   - The LangGraph orchestration (`graph.py`) is domain-agnostic; adding a new domain (superconductors, batteries, catalysis) requires zero changes to the graph.

4. **Reliability as a feature**:
   - 30+ offline tests: the whole agent (graph, hypotheses, experiment plan included) runs end-to-end with a fake LLM/adapter — **no API keys needed**, CI-friendly.
   - Golden-set evaluation harness (field recall / numeric error / fabrication rate) in `eval/`.
   - Hypothesis verdicts (supported / refuted / inconclusive) are computed in code from canonical SI variables — never judged by the LLM.

---

## 📁 Repository Structure

```
├── src/thermolit/                      # Core package
│   ├── config.py                       # Env loading (python-dotenv) & tuning knobs
│   ├── json_utils.py                   # Fence-aware JSON extraction + retries
│   ├── schemas.py                      # Pydantic extraction contract (+ retry feedback)
│   ├── physics.py                      # Thermoelectric physics engine (units, WF decoupling, zT audit)
│   ├── hypothesis.py                   # Structured falsifiable hypotheses + deterministic verification
│   ├── doi.py                          # DOI registry validation (doi.org handle API)
│   ├── adapter.py                      # Sciverse API adapter (lazy client, retries, dedup)
│   ├── graph.py                        # Domain-agnostic LangGraph orchestration (10 nodes)
│   ├── export.py                       # Markdown report -> docx
│   ├── api.py                          # FastAPI service (POST /survey, GET /jobs)
│   ├── cli.py                          # `thermolit` CLI (--profile/--verify/--checkpoint/--export_docx)
│   └── profiles/                       # DomainProfile plugins
│       ├── base.py                     #   interface + generic behaviors
│       └── thermoelectric.py           #   first profile (transport decoupling loop)
├── tests/                              # Offline test suite (no API keys needed)
├── eval/                               # Golden-set evaluation + real-model smoke (--live/--replay)
├── .github/workflows/ci.yml            # CI: lint + offline tests (py3.11/3.12)
├── pyproject.toml                      # Packaging + console script + extras (server/export/checkpoint)
├── Dockerfile                          # docker run -> FastAPI service
├── ROADMAP.md / CHANGELOG.md / CONTRIBUTING.md
├── run_survey.py / test_agent.py       # Thin compatibility entry points
└── .env.example                        # Credentials template (auto-loaded from .env)
```

Serve it as an API:

```bash
pip install ".[server]"
uvicorn thermolit.api:app --port 8000          # or: docker build -t thermolit . && docker run -p 8000:8000 thermolit
curl -X POST localhost:8000/survey -H "content-type: application/json" -d '{"query": "PbTe zT decoupling"}'
```

---

## 🚀 Quickstart Guide

### 1. Installation

Ensure Python 3.11+ is installed, then clone the repository and install:

```bash
git clone https://github.com/0G-Bhqc/ThermoLit-Surveyor.git
cd ThermoLit-Surveyor
pip install -e ".[dev]"       # editable; on Windows with non-ASCII paths use: pip install ".[dev]"
python -m unittest discover -s tests -v   # offline test suite, no API keys needed
```

### 2. Environment Credentials Setup

Copy `.env.example` to `.env` (auto-loaded via python-dotenv) or export environment variables directly:

```bash
# On Linux/macOS
export SCIVERSE_TOKEN="your_sciverse_token_here"
export DEEPSEEK_API_KEY="your_deepseek_api_key_here"

# On Windows (PowerShell)
$env:SCIVERSE_TOKEN="your_sciverse_token_here"
$env:DEEPSEEK_API_KEY="your_deepseek_api_key_here"
```

> **Note**: Obtain your Sciverse Token from [sciverse.opendatalab.com](https://sciverse.opendatalab.com) and DeepSeek API Key from [platform.deepseek.com](https://platform.deepseek.com). Any OpenAI-compatible endpoint works via `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`.

### 3. Run Literature Survey Agent

Execute the default survey pipeline (thermoelectric profile, Bi2Te3 by default):

```bash
thermolit                                  # or: python run_survey.py
```

Run a custom material query:

```bash
thermolit --query "PbTe thermoelectric lattice thermal conductivity phonon scattering" \
          --output_report "pbte_survey_report.md"
```

As a Python library:

```python
from thermolit import run_agent, evaluate_hypotheses, THERMOELECTRIC_PROFILE

state = run_agent("PbTe thermoelectric zT decoupling", profile=THERMOELECTRIC_PROFILE)
print(state["audit_table_md"])      # deterministically computed audit table
print(state["hypotheses"])          # structured falsifiable hypotheses (SI vars + thresholds)
print(state["experiment_plan"])     # experiment matrix, targets = canonical variables
print(state["deep_gap_report"])     # grounded survey report

# After the lab runs: verify measured results (SI) programmatically
verdicts = evaluate_hypotheses(state["hypotheses"], {
    "S": -1.8e-4, "sigma": 1.2e5, "kappa": 1.3, "T_K": 350})
# -> [{"id": "H1", "status": "supported" | "refuted" | "inconclusive", ...}]
```

Or from the command line (verification mode, no survey run):

```bash
thermolit --verify results.json            # results.json: {"measurements": {"S": ..., "sigma": ...}}
# prints per-hypothesis verdicts + refluxes missing variables into next-round gap queries
```

---

## 🆕 What's New in 0.3.0 (the research loop after the survey)

- **`hypothesize` node**: the audit table feeds *structured falsifiable hypotheses* —
  every criterion must be a canonical SI variable + numeric threshold (+ optional temperature),
  validated deterministically (`hypothesis.normalize_hypotheses`): hallucinated variables,
  non-numeric thresholds and criterion-less "hypotheses" are rejected; DOIs outside the
  audit table are tagged.
- **`design_experiments` node**: hypotheses → experiment matrix, deterministically checked
  (measurement targets must be canonical variables; hypothesis refs must exist).
- **Deterministic verification**: `evaluate_hypotheses` derives PF / zT / κ components from
  measured SI values, judges every criterion in code, and refluxes missing variables into
  next-round survey gap queries (`missing_to_gap_queries`) — the loop closes.
- New CLI mode `thermolit --verify results.json`; survey JSON output now carries
  `hypotheses` / `experiment_plan` ready for verification. Workflow: 8 → **10 nodes**.

---

## 🆕 What's New in 0.2.0 (Physics constraints now actually computed)

- **Deterministic physics audit**: new `physics.py` computes the Wiedemann-Franz decoupling
  (`κ_e = L·σ·T` with a Seebeck-adaptive Lorenz number), `κ_l = κ_tot − κ_e`, and
  `zT_calc = S²σT/κ` in code. It flags negative `κ_l`, >30% mismatch between reported and
  computed zT, and sub-amorphous `κ_l`. The synthesized report must treat the
  programmatically generated *Physics Audit Table* as the single source of numeric truth.
- **Data-driven gap retrieval**: missing parameters are now detected by unit parsing and
  field validation (not by LLM self-assessment); follow-up queries are generated from real
  gaps, and the material system is auto-voted from extractions (Bi2Te3 hardcoding removed).
- **Robustness**: automatic `.env` loading, fence-aware JSON parsing, extraction errors kept
  separate from clean records, paper deduplication across passes, parallel extraction,
  exponential-backoff retries, new CLI flags `--top_k/--followup/--log_level`.
- **Open-source scaffold**: src layout, hatchling packaging, `thermolit` console script,
  GitHub Actions CI (offline tests on py3.11/3.12), golden-set evaluation harness,
  30 tests (unit + offline end-to-end with monkeypatched LLM/adapter, no API keys needed).
  See [ROADMAP.md](ROADMAP.md) for the full project plan.

Workflow: pass1_search → pass1_extract → **pass1_audit** → query_refine → pass2_search → pass2_extract → **pass2_audit** → **hypothesize** → **design_experiments** → synthesize
(then, after the lab runs: `thermolit --verify` closes the loop)

---

## 🧪 Running Tests

Unit and offline end-to-end tests need no API keys; real-API integration tests run
automatically when `SCIVERSE_TOKEN` is configured:

```bash
python -m unittest discover -s tests -v    # or: python test_agent.py
```

---

## 📜 License

This project is licensed under the [Apache-2.0 License](LICENSE).
