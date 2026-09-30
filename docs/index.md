# ThermoLit-Surveyor

**缺口驱动、物理约束的研究闭环智能体框架** —— 覆盖文献调研之后的环节:

```text
文献调研 → 结构化可证伪假说 → 实验方案设计 → 实验结果程序化回验 → 新一轮缺口
```

每个环节之间都有**确定性的领域审计层**:报告里的每一个数值都由程序计算、可溯源到 DOI、可离线测试。领域知识通过 `DomainProfile` 插件接入,首个 profile 为**热电输运**(Seebeck / σ / κ / zT)。

## 为什么不同

通用 DeepResearch 智能体止步于一份报告,且合成阶段的数值由 LLM 自由生成、无法审计。ThermoLit-Surveyor:

1. **数值不由 LLM 产生** —— 在代码中确定性地计算 `κ_e = L·σ·T`(Wiedemann-Franz,自适应 Lorenz 数)、`κ_l = κ_tot − κ_e`、`zT_calc = S²σT/κ`,程序生成的《Physics Audit Table》是报告合成的唯一数值基准;
2. **假说是可回验的对象** —— 判据必须是规范 SI 变量 + 数值阈值(+温度条件),由代码归一校验;实验值回来后逐判据程序判定 supported / refuted / inconclusive;
3. **闭环出口** —— 回验中无法判定的缺失变量自动回流为下一轮调研的定向查询;
4. **离线可测** —— 整个智能体(含图编排、假说、实验方案)可在无 API key 环境端到端测试。

## 快速上手

```bash
pip install -e ".[dev]"        # Windows 非 ASCII 路径用 pip install ".[dev]"
python -m unittest discover -s tests -v   # 71+ 离线测试,无需 API key
thermolit --query "PbTe thermoelectric zT decoupling"
```

详见 [使用指南](usage.md)。项目状态与里程碑见仓库 [ROADMAP](https://github.com/0G-Bhqc/ThermoLit-Surveyor/blob/main/ROADMAP.md)。
