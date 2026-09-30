"""领域 profile 插件:每个 profile = 抽取 schema + 确定性审计引擎 + 数值基准表 + 合成指令。"""
from thermolit.profiles.base import DomainProfile
from thermolit.profiles.thermoelectric import THERMOELECTRIC_PROFILE

__all__ = ["DomainProfile", "THERMOELECTRIC_PROFILE"]
