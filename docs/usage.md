# 使用指南

## 安装

```bash
git clone https://github.com/0G-Bhqc/ThermoLit-Surveyor.git
cd ThermoLit-Surveyor
pip install -e ".[dev]"     # Windows 路径含中文时:pip install ".[dev]"
```

可选 extras:`server`(FastAPI)、`export`(docx)、`checkpoint`(断点续跑)、`ui`(Gradio)。

## 凭证配置

复制 `.env.example` 为 `.env`(python-dotenv 自动加载):

```ini
SCIVERSE_TOKEN=...            # sciverse.opendatalab.com 注册
DEEPSEEK_API_KEY=...          # 或任意 OpenAI 兼容端点
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
# 可选
THERMOLIT_CACHE=eval/cache/runs.db   # 启用结果缓存
```

## 命令行

```bash
thermolit --query "PbTe thermoelectric zT decoupling"          # 完整研究闭环调研
thermolit --export_docx report.docx                             # 同时导出 docx
thermolit --checkpoint run.db                                   # 断点续跑
thermolit --no-doi-check                                        # 关闭 DOI 核验

# 实验结果回验(闭环最后一环,不执行调研)
thermolit --verify results.json        # {"measurements": {"S": -1.8e-4, "sigma": 1.2e5, ...}}
```

## Python 库

```python
from thermolit import run_agent, evaluate_hypotheses, THERMOELECTRIC_PROFILE

state = run_agent("PbTe thermoelectric zT decoupling", profile=THERMOELECTRIC_PROFILE)
state["audit_table_md"]       # 程序计算的审计表(报告的数值基准)
state["hypotheses"]           # 结构化假说(规范变量 + 阈值)
state["experiment_plan"]      # 实验方案(测量目标均为规范变量)
state["metrics"]["llm_usage"] # token 计量

verdicts = evaluate_hypotheses(state["hypotheses"], {"S": -1.8e-4, "sigma": 1.2e5,
                                                     "kappa": 1.3, "T_K": 350})
```

## 结果缓存

设置 `THERMOLIT_CACHE` 后,同一 (prompt, model) 的 LLM 调用与同一 (query, top_k) 的检索
直接命中 SQLite 缓存——评测迭代、演示复跑零重复消耗。命中情况见 `metrics.llm_cache`。

## 测试

```bash
python -m unittest discover -s tests -v   # 离线测试,CI 无密钥全绿
python eval/real_model_smoke.py           # 真实模型端到端(--live 需可用 key)
```
