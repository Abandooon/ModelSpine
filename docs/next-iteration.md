# 下一轮：版本化任务合同与固定目标验收

状态：2026-09-23 设计，尚未实现。代码基线为 `ec8e3a3296ee8df767ad513b7a25de0ac1916e01`；该版本的 69 项测试属于上轮工程证据，本设计没有新增运行结果。当前能力见[支持矩阵](foundation-boundaries.md)。

## 1. 目标与退出条件

使候选模型接受事先固定的任务要求检查，并明确区分模型合法、已声明目标满足、意图仍未决及独立评价结果。候选修改不能同时替换任务目标后继续冒称完成原任务。

完成时应能从版本化来源和任务合同加载一项有限任务，预览候选，执行固定目标检查，再通过已有 kernel 保存合格候选；错误、未知或必需意图未决时保留原因。另有独立实现的参考验收揭露“候选与开发检查共同错误”的工程反例。该反例不等于已完成合同忠实性算法或比较研究。

这轮落在公共任务边界、P1-A 输入语义、P2-A/B 的有限检查消费者及 E0 验收设计交界。它不是完整 P1 实现，也不包含九模块全部实现。

## 2. 为什么现在做

当前内核能核对候选、计划、范围及报告，但不会自行判断计划是否忠实于用户目标。现有自动机 CLI 同时修改转移和 `machine.trace`，证明了新的模型和输入组合可运行；它没有证明原先固定的输入仍被正确处理。

因此先把目标与候选分开管理，为随后的需求澄清、生成修复和代码恢复提供共同验收入口。当前无需先实现通用迁移、自动语言理解、Studio 界面或完整实验运行器。

## 3. 三种材料与可见范围

| 材料 | 拥有者与内容 | 可见性及权力 |
|---|---|---|
| TaskContract：任务合同 | 任务提供方确定；身份、原始来源、目标声明、未决项、初始模型引用、固定开发检查计划及声明—义务映射 | 方法可读取；一次运行开始前固定，模型提案无写权；是结构化输入，不是自动形式化的成果 |
| TaskCard：工程/研究任务卡 | apps/studies 装配；钉住任务合同和输入引用，规定允许信息、预算、记录位置和评价方式 | 是编排材料；论文条件和评价文件位置不能进入运行包 |
| EvaluationSpec：独立评价规格 | 评价方预先制定；留出输入/期望、目标来源、工具版本及构造依据 | 不传给候选生成/修复接口；输出只用于评价。当前公开工程样例可被开发者看到，不能冒称安全隔离的隐藏研究集 |

开发义务可以作为方法反馈；留出评价不能被偷偷用于生成、选择候选或决定重试。独立性来自目标建立和推导路径，不是文件分开或工具改名；本轮人工编写的工程规格须记录共同作者/来源，不能冒称已获得独立专家真值。

## 4. 最小合同选择

复用 `ArtifactRef`、`EvidenceRef`、`SnapshotRef`、`CheckPlan`、`ValidationReport` 和 `ChangeProposal`。不往现有严格 v0.1 JSON 偷加字段，不把任务哈希塞入 assumptions 文本冒充绑定。

TaskContract 和 TaskAssessment 是 assurance 与 apps 之间的实际交换对象，由 protocols 唯一定义，并使用独立的任务信封 schema_version。PreparedTask 及任务评估逻辑归 assurance，文件读取和运行上下文固定归 apps。研究 TaskCard、EvaluationSpec 和未实施的会话对象不放入 protocols；本轮不建立通用注册中心。

| 对象 | 必须承载的最小信息 |
|---|---|
| TaskContract | 独立 schema_version、id/version；初始 SnapshotRef；带 ID、正文、类别、确认状态和来源引用的目标声明；哪些未决项影响必需目标；固定 CheckPlan 或明确的无可执行计划状态；义务 ID/version 到声明 ID 的显式映射 |
| PreparedTask | 通过校验的 TaskContract、外部钉住的 ArtifactRef、规范化计划及其哈希（无计划则均为 None）；不可变，不暴露修改计划的入口 |
| TaskAssessment | task_ref、candidate SnapshotRef、完整开发 ValidationReport；未形成候选/未检查时引用或报告允许 None 并列原因；独立的意图就绪状态、声明覆盖及目标检查状态。它只描述评估，不包含未来提交事实；commit/未提交原因由 apps 的运行结果关联 |

TaskContract 自身不存其自身字节哈希。任务提供方在 TaskCard 中钉住其 ArtifactRef；应用读取原始字节，assurance 逐字节核对任务及来源身份、版本、哈希和已登记位置。来源只支持 UTF-8 文本及 `lines:start-end` 定位（从 1 开始、包含两端），使用显式传入的制品引用→路径映射，不遍历任意来源或回退到旧文件。

正文中 `intent/fact/hypothesis` 与确认状态分别保存。必需目标由有出处的已确认 intent 授权；fact 只能作为支持证据，hypothesis 作为明确采用的条件，确认假设不使其自动成为用户目标。工程样例的确认者注明是任务作者，不冒称真实用户。来源格式或哈希匹配不证明内容真实。必需目标未确认、存在冲突或缺少必要映射时，整体完成状态必须未决；已知义务的检查结果仍如实保留。

范围之外的自然语言不尝试推理。声明到检查义务的映射由任务作者明确给定并审查；不按关键词猜义务，也不把“找到了映射记录”称为语义忠实。

## 5. 接口与接受边界

以下为下一编码轮拟实施的接口语义，名称可随现有代码风格调整，职责不可隐式合并：

```text
load_task(path, expected_task_ref, source_paths) -> PreparedTask  # apps
prepare_task(contract_bytes, expected_task_ref, source_contents) -> PreparedTask  # assurance
assess_task(prepared_task, snapshot, checker) -> TaskAssessment  # assurance
run_task(prepared_task, metamodel, snapshot, proposal, checker, actor) -> task run result  # apps
evaluate_candidate(snapshot, evaluation_spec) -> EvaluationResult  # 评价侧
```

`load_task` 仅按显式路径读取任务和来源字节并调用 prepare_task，不拥有解释/降级规则。`prepare_task` 纯内存处理严格解码、字节身份、来源位置及声明—义务映射，固定目标范围与计划。重复 ID、错来源、未知字段、引用不存在的声明/义务等明确报错；合法必需声明尚无对应义务或已登记待补意图则列未决，不能补默认答案。承诺存在的来源文件不可读/哈希不符是错误，显式登记待补的来源是未决，两者不合并。

没有任何可执行义务时，任务信封允许 plan=None 并列原因，TaskAssessment 的 report=None 且目标为未检查/未决；不能创建空 CheckPlan 或恒真义务获得通过。有部分已知义务时正常执行它们，同时保留未覆盖目标。

无计划分支在核对输入身份后、装配 kernel 之前早退：candidate_ref=None、report=None，基准仍由 TaskContract 的初始 SnapshotRef 定位；不执行候选 preview 或提交。assess_task 接受此明确未形成候选状态，只有存在计划时才要求候选 Snapshot。现有 kernel 要求非空计划，不为这条分支弱化该合同。

任务/来源的 ArtifactRef 哈希均指原始字节，prepare_task 直接核对收到的 bytes；CheckPlan 的 digest 仍是现有规范对象哈希。记录中的 task_file_sha256 与 plan_hash 名称分开，不能通过重序列化推算原文件哈希。任务引用由可信调用方在候选产生前固定；哈希一致不代表候选有权选择另一任务。跨进程持久化授权不在本轮范围。

`assess_task` 检查 task↔计划/目标声明的绑定并调用显式 Checker，输出逐项报告和未决项，不获得模型写权。候选/计划/范围/义务完整性的共同报告校验由 protocols 提供给 assurance/kernel 复用；调用方传入预期范围，不能以报告自报的范围决定完整覆盖。实现时从已有内核校验提取最小公共函数，保留旧拒绝行为，避免两套判断逐渐分叉。assurance 不导入有限模型适配器。

`run_task` 由应用装配 kernel。绑定的 Checker 每次调用都核对实际计划与 PreparedTask 的固定计划一致，再执行有限语义检查；kernel 仍执行公共报告校验并独占保存事务。任务输入与初始模型的身份、元模型和基准必须吻合，不按名称匹配。候选不会携带替代任务合同、检查器或评价文件位置。初次执行绑定合同中的初始快照；后续改变目标/基准另建明确任务版本，不自动把旧任务重放到最新模型。

处理次序为：加载固定上下文 → 校验候选基准 → preview → 固定开发义务 check → 记录目标/意图状态 → 合格时 decide/apply。默认仅在必需意图已明确且开发义务全部 satisfied 时保存；其余返回诊断且本入口不提交。kernel 原有 checked-save 仍是独立的残余保存能力，不能被本入口用来标记任务完成。

独立评价在评价侧对终候选/已保存版本执行，结果另记。若开发检查通过而留出评价失败，保留真实模型保存与评价失败两个事实；不伪造回滚，不把留出结果偷喂给方法。工程测试也应直接对未提交候选运行参考验收，用于检查边界；这不改变生产保存策略。

只有结构化声明范围内的成功可写“已声明目标满足”，不能写成全部用户意图完整、业务许可或应用交付。

## 6. 两类有限目标规则

沿用结构与有限行为两种能力作为工程见证；公共任务信封不含永久的 profile 枚举，行业名称、图节点名及输入符号不是框架默认。

| 规则 | 输入与执行语义 | 重要限制 |
|---|---|---|
| `graph_reachability` | 目标为图根，field 以现有 root 作定位锚点；参数 source、destination、expected_reachable。按固定端点 ID 遍历实际边 | 与结构合法性/无环义务组合；非法端点、嵌套或坏依赖先报告，不能把无效图当作“不要求可达”的成功 |
| `trace_acceptance` | 目标为机器根，field 使用 initial；参数 input、expected_accept。输入来自固定 CheckPlan，实际遍历候选转移并判断接受 | 不读取候选 machine.trace 作为任务输入；先验证机器合法、确定且在支持范围内，无效机器不能通过 expect_accept=false 蒙混过关 |

可达性包含零长度路径，即同一有效节点可达自身。自动机缺少某一步转移或终态不接受，是受支持输入上的正常拒绝；输入字符超出声明字母表则为 unknown/未支持，不能计为负向期望成功。参数类型错误为 error。

两个新规则放在显式适配器，通过现有 Checker 合同接入。现有 `directed_acyclic_graph`、`deterministic_automaton` 和可编辑输入的 `finite_trace_acceptance` 保持原义；新规则用新名称/工具版本，不覆盖旧运行语义。Obligation.parameters 现有标量已能表达本轮参数，无需先扩原生引用/集合。

未知规则为 unknown，已知语义反例为 violated，参数/来源/绑定或执行错误为 error；不得转换为通过。whole-model 依赖继续保守 incomplete，证据适用性保持 unknown/stale，本轮不实现安全全图 current。

参考验收在测试/研究侧用独立实现：图可达使用不同遍历实现，自动机按规格中的固定输入展开状态序列；不得调用被评 Checker、复用其执行结果或从候选 trace/开发报告反推期望。共享严格协议解码可以，但要记录共同输入来源，并用故意错误的开发规则/绑定验证参考验收会暴露差异。

## 7. 文件归属与实施顺序

下表是下一编码轮的计划文件，不表示已创建实现：

| 顺序 | 计划文件范围 | 交付责任 |
|---|---|---|
| 1 | `packages/protocols/` 的源码/合同/测试；`packages/assurance/src/modelspine_assurance/tasks.py` 及合同/测试；`packages/model-kernel/` 的报告校验调用 | 任务信封、通用任务评估、实际复用的报告完整性校验；assurance/kernel 仅依赖 protocols |
| 2 | `adapters/task_checks.py`；必要时小改 `adapters/finite_models.py` | 两条新任务规则；仅依赖 protocols，旧规则回归不变；若抽取语义辅助，只为这两个真实消费者 |
| 3 | `apps/task_contracts.py`、`apps/task_acceptance.py` | 显式本地文件读取、路径边界和固定上下文；CLI 完整调用预览、评估、决定和保存流程 |
| 4 | `domain-packs/structural-graph/tasks/`、`domain-packs/finite-automaton/tasks/` | 版本化公开来源片段、任务合同及固定开发义务；不改旧样例目标来配合新候选 |
| 5 | `tests/support/task_oracle.py`、`tests/fixtures/task-acceptance/`、`tests/test_task_acceptance.py`、现有导入边界测试 | 独立参考实现、评价规格与正反验收；评价端只能向方法提供预定的公开反馈 |
| 6 | `docs/`、apps/adapters 说明；`studies/lifecycle/` 的任务卡设计说明 | 支持矩阵、调用示例、版本身份/成本字段与后续研究接入说明；不新增统计运行器 |

apps 装配 assurance、kernel 与检查器；能力包不导入 apps/studies/tests。TaskContract 是任务语义合同，TaskCard 中的论文条件、预算及 EvaluationSpec 不得反向进入它。assurance 增加通用任务评估，有限领域规则仍由适配器提供，不能在 implemented_scope 中混记为内置规则。

protocols/assurance 因真实供应/消费任务信封而扩展，kernel 只复用原有报告校验逻辑；不增加任务/论文条件分支。generation 不新增生成算法，新增任务规则仍是 terminal-only。实际变更包按消费者兼容性升版，不统一升级九模块。requirements、interaction、implementation、code-intelligence、component-reuse 继续 planned。

## 8. 必须通过的验收

1. 两类任务都存在明确正例，固定目标检查通过并提交；初始模型、任务/计划/候选引用和输出结果可核对。
2. 图保持合法无环但破坏任务指定可达性：结构检查通过，固定目标 violated，本入口不保存。
3. 自动机改转移并同步改 machine.trace，使旧样例内部检查通过：固定原输入仍被检查，错误候选被拒绝；禁止靠替换输入获得原任务成功。
4. expect_accept=false/expected_reachable=false 有正常正例；坏机器/图、非法参数不能被当成满足负向期望。
5. 改名不改身份/行为时目标结果不变；改变与目标相关的边、转移或接受态会改变结果。
6. 任务/来源/计划/候选或元模型错版本、错哈希、旧基准、错报告均明确拒绝，既有已接受状态不变。
7. 必需意图未决、冲突或来源无法定位时不宣称任务完成；不支持规则保留 unknown，已知结果不抹去。
8. 候选与开发规则共享语义错误时，保持正确且固定的任务/计划/报告绑定，参考验收仍可出现“开发通过、独立评价失败”；完整保留两份结果。不能用错哈希被拒的完整性反例替代此项，也不能将注入反例记为自然失败率或论文效果。
9. 更改任务目标必须建立新版本/新运行，旧任务结果不能冒用；本轮约束为单次运行中固定上下文，不宣称已有跨进程任务仓库或永久版本注册表。
10. 新入口不会导入评价实现；运行包不导入 apps/studies/tests；原 69 项行为回归继续通过，新增测试按真实边界组织，不预填数量代替验收。

## 9. 执行范围与停止条件

只使用现有 Python 标准库、本地结构化材料和显式候选。不实现自然语言抽取、问题排序/答复会话、自动表示缺口证明、元模型迁移、LLM 调用、外部求解器、应用运行时或 UI；不完整修复旧来源框架。表达不了的目标明确 unsupported/unknown，不能临时缩目标后宣称完成原任务。

完整流程和上述反例成立即结束本轮，不追加其他方向实现。源码与公开说明按现有授权提交指定 GitHub；运行日志、源文件哈希及失败结果另记，历史代码只用 Git 保存。比较研究的预算/样本量由后续协议决定，本轮不预填科研数字。

随后 P1 的首个真实消费者可实现“可信结构化来源 → 多个有限解释 → 有区分力的问题/答复 → 模型提案”，复用本轮固定目标验收；P2 再推进忠实性/相关错误机制。P4 的恢复输出也可消费同一目标边界，P3 的任务交互与 E 的正式比较按各自启动条件推进，均无需等其他论文发表。
