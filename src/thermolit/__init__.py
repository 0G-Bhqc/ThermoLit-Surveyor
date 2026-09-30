"""
ThermoLit-Surveyor — 缺口驱动、物理约束的科研文献调研与研究闭环智能体框架。

核心思想:在"检索 → 抽取 → 合成"之间插入一个**确定性领域审计层**,
报告中的每个数值都由程序计算并标注来源,LLM 只负责组织与解释,不负责产生数字;
调研之后延伸出研究闭环:结构化可证伪假说 → 实验方案设计 → 实验结果程序化回验,
回验缺失的变量自动回流为下一轮调研缺口。

    from thermolit import run_agent, THERMOELECTRIC_PROFILE
    state = run_agent("PbTe thermoelectric zT decoupling", profile=THERMOELECTRIC_PROFILE)
"""
from thermolit.graph import build_survey_app, run_agent
from thermolit.hypothesis import evaluate_hypotheses
from thermolit.profiles.base import DomainProfile
from thermolit.profiles.thermoelectric import THERMOELECTRIC_PROFILE

__version__ = "0.6.1"

__all__ = ["DomainProfile", "THERMOELECTRIC_PROFILE", "build_survey_app",
           "evaluate_hypotheses", "run_agent", "__version__"]
