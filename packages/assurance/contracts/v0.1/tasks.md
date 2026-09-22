# 固定任务准备与评估合同

状态：2026-09-23 本轮实现合同，源码、单包和集成验收已完成。源码入口为 [tasks.py](../../src/modelspine_assurance/tasks.py)，共享交换字段由 [protocols](../../../protocols/contracts/v0.1/README.md) 唯一定义；本页不新增另一份 JSON 结构。旧 `check` 的字段规则保持原合同，有限图/自动机规则仍归适配器。

本入口把已声明目标、来源与检查计划固定下来，输出意图就绪和目标检查两种状态。它不自动抽取自然语言，不证明映射忠实，不写模型，也不获得业务或应用交付许可。

## 公开入口与拥有者

```python
prepare_task(
    contract_bytes: bytes,
    expected_task_ref: ArtifactRef,
    source_contents: Mapping[ArtifactRef, bytes],
) -> PreparedTask

assess_task(
    prepared_task: PreparedTask,
    snapshot: Snapshot | None,
    checker: Checker,
) -> TaskAssessment
```

PreparedTask 是本包拥有的不可变进程内值，包含 contract、task_ref、plan_hash、mapped_statements、unresolved。plan_hash 在 contract.plan=None 时为 None。通过 prepare_task 建立它；这是可信调用方之间的装配边界，不是防任意 Python 代码伪造的安全令牌或跨进程授权系统。

apps 的 `load_task` 按显式路径读取字节，再调用 prepare_task。assurance 不遍历目录、不读文件、不选择后备来源或检查器；运行依赖只有 protocols 和标准库。

## 来源与任务完整性

调用方在产生候选之前选定 expected_task_ref。prepare_task 对原始 bytes 计算 SHA-256，核对任务引用，再严格解码 `task-contract/0.1`。任务 id/version 与引用 artifact_id/revision 相同，任务 base.project_id 与引用 project_id 相同；base 引用格式必须完整合法。具体初始模型和元模型内容由 apps/kernel 加载校验。

任务/来源引用的 content_hash 指原始文件字节，不是重新序列化 JSON 的哈希。CheckPlan 的 plan_hash 使用协议已有规范对象 digest；两种哈希不可混用。改变文件排版也会改变其原始字节身份。

声明 ID 唯一且 ID/text 非空。pending_reason 只能为 None 或非空文本。无来源的声明必须显式登记 pending_reason；confirmation 为 unresolved/conflicted 时也必须有原因。已声明存在的每个来源都必须在 source_contents 中给出原始 bytes，内容须为 UTF-8 且哈希一致。定位仅支持 `lines:start-end`，从 1 开始、包含两端且不越界；不提取正文来猜测目标含义。

来源、定位和哈希匹配只建立内容可追溯性，不认证作者、真实用户或文本真值。当前工程例中的 confirmed 来源由任务作者声明，不能说成已得到真实用户确认。

## 义务映射与未决状态

plan 存在时仍遵守原 CheckPlan 的非空合同；bindings 必须恰好覆盖其中每个义务。一个义务对应一条绑定，义务 ID/version 必须匹配，statement_ids 非空、唯一且指向已有声明。重复、悬空或错版本的绑定是完整性错误；有映射记录不证明检查语义忠实。

合法声明可以尚未映射。只有 required 声明用于判定意图是否就绪：它必须为 intent、confirmation=confirmed、有来源、没有 pending_reason 且至少被一个义务映射。任一条件未满足则列入 unresolved。没有 required 声明或 plan=None 也保持 unresolved；可选声明的待补项不自动阻止所有任务。

fact 只能支持目标，hypothesis 可表达明确采用的条件；即使 confirmed，把它们标为 required 也不能代替用户目标而获得 ready。confirmation 与 category 保持不同含义。本入口按显式 required 标记处理范围，不判断任务是否已经包含全部应有目标。

plan=None 时 bindings 必须为空。assess_task 要求 snapshot=None，不运行 Checker，返回 candidate=None、report=None、goal_status=not_checked。应用必须在装配 kernel/preview 之前处理此分支，不制造空计划或恒真义务。有部分义务时仍执行全部已知项，同时保留未覆盖的必需声明。

## 候选、报告与状态

有计划时 assess_task 要求实际 Snapshot，与任务 base 的 project/model/metamodel 及元模型哈希一致；修订不得早于 base。同一修订必须与 base 完整引用相同。后续修订并不由本函数证明历史祖先关系，初始基准与合法变更链仍由 apps/kernel 负责。

assess_task 每次复核固定 plan_hash，以 `select_scope(plan)` 选择全部计划目标，再调用显式 Checker。返回报告经公共 `validate_report(report, snapshot, plan, scope)` 核对候选/计划/范围/前提、工具身份/版本和完整唯一的义务 ID/version 覆盖。调用方的预期范围不能来自报告自报值；不允许局部报告冒充完整任务检查。

| TaskAssessment 字段 | 本轮语义 |
|---|---|
| intent_status | unresolved 非空则为 unresolved，否则 ready；不依赖检查是否通过 |
| goal_status | 全部义务 satisfied 才为 satisfied；否则逐项有 error 优先为 error，其次有 violated 为 violated，其余为 unknown；无计划为 not_checked |
| mapped_statements | 已映射声明 ID 的排序集合；不表示语义忠实或完整用户目标覆盖 |
| unresolved | 对必需声明和无计划状态的可读诊断；不得解析文本作为控制逻辑 |
| report | 保留逐项开发结果，聚合状态不抹去 unknown/not_applicable/error 等残余；无计划时为 None |
| candidate/task_ref | 实际候选引用与外部事先固定的任务引用；评估中不包含 commit |

本包不导入适配器，检查器仍是可信执行依赖。完整报告绑定不证明规则正确、实际读取依赖完整或独立真值；检查范围不是自动读集。全图依赖不完备时仍按既有合同保留证据适用性 unknown/stale。

## 错误与模型保存

| 情况 | 可观察结果 |
|---|---|
| 错形状/版本、空声明、非法定位或映射 | ContractError，code=invalid |
| 任务/来源哈希错配、任务身份、义务版本、计划、候选或报告绑定冲突 | ContractError，code=conflict |
| 已声明来源未提供；apps 无法读取明确路径 | ContractError，code=not_found |
| 合法但必需意图待补、冲突、无映射或无计划 | 正常评估保留 unresolved；无计划为 not_checked |
| Checker 返回合约内 unknown/violated/error 等 | 保留逐项报告及对应聚合状态 |
| Checker 执行异常或非法报告 | 异常传播或公共校验拒绝，不伪造成功、不自动换实现 |

apps 的 run_task 先核对初始 SnapshotRef 与元模型，再经 kernel.preview 产生候选。仅在 assessment.intent_status=ready 且 goal_status=satisfied 时调用原有 decide/apply；内核仍复核报告并独占事务。TaskRunResult 将评估、候选、已接受快照、commit 或未提交原因分别返回。checked-save 不是本入口的后备策略。

测试/研究侧另行固定 EvaluationSpec，以独立实现检查候选；任务 CLI 不导入或执行它。开发检查通过而参考验收失败时保留两份真实结果，不伪造回滚。工程样例的公开规格和共同作者不构成盲测研究真值，也不证明比较优势。
