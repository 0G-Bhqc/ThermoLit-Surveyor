# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与语义化版本。

## [Unreleased]

### 计划中(见 ROADMAP M1)
- 金标草稿人工核对(20~50 篇;`eval/golden_draft.py` 已把成本降为逐条核对)
- 20~50 篇真实热电文献金标评测集与 F1 报告

## [0.6.1] — 2026-09-30

### Added(检索策略优化,真实 A/B 验证)
- **数值密度预筛(fetch-and-rank)**:检索多取一倍候选,按"数字+输运单位"密度
  排序后截取——缓解真实校准发现的"综述性段落占比过高"问题。
  真实 A/B(同 query 同 top_k):含数值记录率 44%(4/9)→ 62%(5/8)。
- **缺口查询数值导向**:query_refine 提示词强制"参数+测量关键词+目标数字",
  禁止综述型查询(真实 run 的 followup 已带 measured/W-mK 等词)。
- **金标草稿生成器**(`eval/golden_draft.py`):把调研输出转成带 excerpt 与程序
  解析 SI 值的草稿 JSONL,标注工作量降为"逐条核对"。真实 PbTe 调研已产出
  8 条草稿(5 条含待核对数值)。
- CLI 输出新增 `papers`(检索段落,供金标草稿与证据回溯)。
- 测试 101 → **105**。

### Fixed(第二档真实世界校准)
首次以真实 Sciverse + 真实 LLM 跑通全链路(PbTe,9 篇文献/146K tokens/764s),
真实环境暴露并修复四个缺陷:
- **适配器 async 兼容**:真实 `sciverse 0.13.x` 的 `semantic_search` 是协程,
  旧实现当同步调用导致永远 0 命中——现自动兼容同步/异步两种 client;
- **DOI 锚点断裂**:真实命中无 `doi` 字段(仅内部 doc_id 哈希)——新增
  Crossref 标题→DOI 解析(difflib 相似度 ≥0.6 防错配,失败保留 N/A 不阻塞),
  证据表增加年份/期刊列;
- **记录层去重**:不同查询命中同一文献时记录重复计入证据链——与检索层同规则去重,
  `metrics.duplicate_records_skipped` 计数;
- **温度回落链**:输运字段无温度时回落到 zT 温度(同一测试通常同温),
  而非错误回落 300K 造成假"温度不一致"标记。
真实数据上生效的证据防线:13 条 LLM 摘录通过包含校验,1 条编造句被 `证据句未核实` 标记。

### 计划中(见 ROADMAP M1)
- 20~50 篇真实热电文献金标评测集与 F1 报告(需人工核对真值;基础设施已就绪,
  `eval/live_readiness.py` 自检外部依赖就绪状态)

## [0.6.0] — 2026-09-30

### Fixed(深度评测 P0 修复)
- **逐字段温度感知(P0-1)**:深度评测发现审计引擎用单一 T 参与全部派生计算,
  在"S@300K、zT@923K"类文献上产生系统性温度错配。现在每个字段解析自己的温度
  (`@ T` / `at T` / room temperature→300K),zT_calc 仅在 S/σ/κ 同温时计算、
  κ_l 仅在 σ/κ 同温时计算;跨温一律拒绝计算并打 `字段温度混计` 标记,
  报道 zT 与计算温度不同时不再给出误导性偏差百分比。抽取 schema 同步约束
  LLM 在值字符串中携带各自温度。
- **证据句包含校验(P0-2)**:`evidence_sentences` 的摘录现在必须(空白归一后)
  真实存在于原文,否则打 `证据句未核实` 标记——封堵 LLM 编造"看起来像原文"的句子。
- **κ 单位解析缺口**:修复 `W/(m·K)` 括号写法解析失败(负样本回归防线抓到)。

### Added
- **负样本回归防线**(`tests/test_physics_negative.py`,14 用例):单位写法长尾、
  跨字段温度、极值与证据校验陷阱——新解析规则必须先在此加用例。
- **live 就绪自检**(`eval/live_readiness.py`):逐项检查 LLM 凭证/sciverse 包/
  token/doi.org 可达性,可选 `--ping` 真实补全,为第二档(真实世界校准)提供
  一键就绪判断。

## [0.5.0] — 2026-09-30

### Added(M2 收尾)
- **结果缓存**(`cache.py`):`THERMOLIT_CACHE=<sqlite 路径>` 即启用——同一 (prompt, model)
  的 LLM 调用与同一 (query, top_k) 的检索直接命中缓存,评测迭代/演示复跑零重复消耗;
  命中统计写入 `metrics.llm_cache`。
- **Gradio 演示界面**(`ui.py`,extra `ui`):输入查询 → 报告/审计表/假说三面板;
  `format_state` 纯函数离线测试覆盖。
- **文档站**:`mkdocs.yml` + docs/(首页/使用/Profile 开发/服务部署/评测),
  `mkdocs serve` 本地预览。
- **发布工程**:sdist/wheel 构建验证;README 增补缓存/演示/文档站说明。

## [0.4.0] — 2026-09-30

### Added(M1 可靠性 + M2 产品化)
- **Pydantic 抽取契约**(`schemas.py`):抽取输出本地 schema 校验,失败把错误信息
  回喂 LLM 重试一次;不依赖各端点参差的 response_format,校验永远在本地。
- **句子级证据引用**:抽取 schema 新增 `evidence_sentences`——每个非 null 参数必须
  附摘录原文的完整句子,数值可回溯到原文(审计 JSON 直带)。
- **DOI 注册库核验**(`doi.py`):调研结束后把全部 DOI(记录 + 假说证据)批量比对
  doi.org handle API(免费);假 DOI 点名为 `missing`,网络失败标 `unknown` 不冤枉;
  CLI `--no-doi-check` 可关。
- **token 用量计量**:`UsageTracker` 代理跨节点累计 input/output tokens 与请求数,
  写入 `metrics.llm_usage`。
- **断点续跑**:`--checkpoint PATH.db` 启用 SqliteSaver(thread_id 由 query+profile
  派生);缺依赖时优雅降级。
- **docx 导出**(`export.py`):`--export_docx OUT.docx` 把 Markdown 报告(标题/段落/
  粗体/引用/列表/表格)转换为 Word 文档,满足提交与分享格式。
- **FastAPI 服务**(`api.py`,extra `server`):`POST /survey` 后台执行 + `GET /jobs/{id}`
  轮询产物 + `/health`;附 Dockerfile(`docker run` 即起服务)。
- 测试 51 → **71 个**(schemas/doi/计量/导出/checkpoint/API 全覆盖,全部离线)。

## [0.3.0] — 2026-09-28

### Added
- **研究闭环:调研之后的三个环节**(本版本核心):
  - `hypothesize` 节点:依审计表生成**结构化可证伪假说**——每条假说的判据必须是
    规范变量(S、σ、κ_l、zT…)+ 数值阈值 + 可选温度条件,由 `hypothesis.normalize_hypotheses`
    确定性校验(幻觉变量/非数值阈值/无判据假说一律剔除,引用审计表外 DOI 打标);
  - `design_experiments` 节点:由假说生成实验方案,`normalize_experiment_plan`
    确定性校验(测量目标必须是规范变量、假说引用必须存在);
  - **确定性回验** `hypothesis.evaluate_hypotheses`:实验测量值(SI)→ 派生变量
    (PF、zT、κ 分量)→ 逐判据比较 → supported / refuted / inconclusive;
    inconclusive 的缺失变量经 `missing_to_gap_queries` **回流为下一轮调研缺口**(闭环出口);
  - CLI 新增 `thermolit --verify results.json` 回验模式(不执行调研)。
- **规范变量语言** `CANONICAL_VARS`:文献抽取与实验测量共用同一套 SI 变量命名,
  是假说判据、实验目标与回验三方能对话的基础。
- 工作流从 8 节点扩展为 **10 节点**;调研 JSON 输出新增 `hypotheses` /
  `experiment_plan` 及其 warnings(可直接作为回验输入)。
- profile 接口新增可选钩子 `build_hypothesis_prompt` / `build_experiment_prompt`
  (`supports_research_loop` 属性);不支持闭环的 profile 自动降级跳过。

## [0.2.0] — 2026-09-28

### Added
- **确定性物理审计引擎 `physics.py`**:从文献文本解析带单位数值(µV/K、S/cm、mΩ·cm、
  mW/cmK、×10⁵ 等),在代码中真实计算 Wiedemann-Franz 解耦
  (`κ_e = L·σ·T`,Lorenz 数随 |S| 自适应插值)、`κ_l = κ_tot − κ_e`、
  `zT_calc = S²σT/κ`;自动标记 κ_l 为负、zT 偏差超 30%、κ_l 低于非晶下限等异常。
  报告以程序生成的《Physics Audit Table》为唯一数值基准,LLM 不得改写数值。
- **DomainProfile 插件架构**(`profiles/`):领域知识(抽取 schema、审计引擎、
  缺口提示、合成指令)与 LangGraph 编排解耦,新增领域零改动编排层;
  首个 profile:`thermoelectric`。
- **缺口驱动检索闭环**:参数缺口由"单位解析失败/字段缺失"数据驱动判定,
  驱动 Pass 2 定向补查;材料体系由抽取结果自动投票,移除 Bi2Te3 硬编码。
- **评测骨架**(`eval/`):金标集格式、评测脚本(字段召回率/数值误差/编造率)。
- **开源工程化**:src 布局、pyproject(hatchling)、`thermolit` CLI 入口(`--profile`)、
  GitHub Actions CI(离线测试矩阵 3.11/3.12)、30 个测试(单元 + 离线端到端)。

### Fixed
- `config.py` 现在通过 python-dotenv 加载 `.env`(此前 README 承诺但从未实现)。
- 移除 `.strip("```json")` 逐字符剥离 hack,替换为围栏感知 JSON 提取。
- 抽取失败的错误记录与正常记录分离,不再污染合成上下文。
- Pass 1/2 论文按 DOI/标题去重。
- `requirements.txt` 移除会被 pip 误装的 `Python>=3.11.0` 行。

## [0.1.0] — 初赛原型

- LangGraph 2-Pass 多跳检索原型:Sciverse 语义检索 + DeepSeek 抽取/合成。
- 已知局限:物理引擎仅存在于提示词(未实现)、Bi2Te3 硬编码、无测试、不加载 `.env`。
