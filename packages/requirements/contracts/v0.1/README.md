# 需求合同 v0.1：有限澄清切片

状态：exercised-subset。本页描述[当前源码](../../src/modelspine_requirements/__init__.py)实际支持的合同；更广的声明分析与诊断仍见[目标设计](../design.md)。[早期样例](examples.json)保留原有设计地位，不是当前 `ClarificationCase` JSON。应用装配和有限样例见[澄清闭环](../../../../docs/clarification.md)。

## 输入、状态与职责

requirements 拥有解释、问题和回答记录，只产生候选提案。运行时只依赖 protocols/标准库；`preview` 与 `observe` 由应用显式注入，图/自动机规则归适配器。应用另行固定后继 `TaskContract`，由已有 kernel 独占模型提交。

| 对象 | 当前字段和语义 |
|---|---|
| `EvidenceNeed` | `id/text/source_refs/pending_reason`；显式待补证据阻止澄清，不以空来源代替完成 |
| `Interpretation` | `id/text/operations/source_refs`；调用方提供的有限解释及其模型操作，空操作表示保留当前模型 |
| `Probe` | `id/text/obligation/source_refs`；固定行为问题模板，有限适配器支持图可达和固定输入串接受，模板期望值必须为 true |
| `ClarificationCase` | `schema_version/id/version/task_ref/base/needs/interpretations/probes/budget`；绑定父任务、初始模型和完整显式候选列表 |
| `Budget` | 非负整数 `max_candidates/max_observations/max_questions`；分别限制候选数、实际观察调用数和已发出问题数 |
| `Observation` | `candidate/probe_hash/status/value/reason`；`observed` 才有布尔值，`unknown/error` 必须保留原因且值为 null |
| `Question` | `id/version/case_ref/task_ref/base/remaining/sequence/probe/predictions`；包含剩余解释与实际行为见证，其规范哈希绑定回答 |
| `AnswerRecord` | `schema_version/id/version/question_hash/status/value/actor`；`answered` 必须携带布尔值，`refused/conflicted` 必须为 null |
| `Session` | 原案例、基准、预览候选、已得观察记录、剩余解释、回答历史、当前问题、已用预算和终止原因；返回新不可变值，不覆盖旧回答 |

所有 JSON 使用 protocols 的严格解码，未知字段、重复键、类型混淆和错误身份均拒绝。案例/回答 `ArtifactRef` 的 SHA-256 指收到的原始 UTF-8 字节；来源仅通过显式引用到字节的映射读取，支持 `lines:start-end` 定位。规范对象哈希用于问题和观察绑定，与原文件哈希分开。

`Session` 是可信进程内值，预览/观察回调的实际语义由装配方负责；它不是可从外部任意反序列化后使用的授权凭证。哈希检查证明内容对应，不证明来源真实性、回答者权限或用户意图忠实性。

## 运行接口

```text
prepare(case_bytes, expected_case_ref, task_ref, metamodel, snapshot,
        source_contents, preview, observe) -> Session
answer(session, question, answer_bytes, expected_answer_ref) -> Session
propose(session, successor_task_ref) -> ChangeProposal | None
```

`prepare` 校验任务/模型/元模型、来源与证据待补情况，再构造至少两个显式解释的候选。候选与观察均核对返回绑定。列表超过候选预算时不截断执行；观察预算中途耗尽时保留已知结果但不据此确认。没有语言范围的解释穷尽证明，也不生成自动的 `mapping_error/model_gap/representation_gap` 结论。

问题只能来自对所有剩余解释均有确定观察、且真假两组都非空的 probe。选择规则是最大化较小分组大小，即 minimax 划分；同分按 probe ID 排序，不使用启发式概率。每发出一个问题消耗一次问题预算。unknown/error 观察不能当作 false；没有可区分问题或问题预算耗尽时返回 `unresolved`。

`answer` 只接受当前问题及其精确内容哈希绑定的回答。回答者不得为空，原字节、身份、版本与项目必须匹配。重复使用回答记录身份、过时或被改写的问题显式冲突；不能用后来的回答覆盖旧记录。显式拒答/冲突记录进入历史后停止为 `unresolved`。有效布尔回答只保留行为对应的解释，继续提问或收敛。

至少存在有效回答且恰好保留一个解释时，状态为 `ready`；如果获选候选的模型元素与初始模型相同，则为 `no_change`。这只表示给定候选列表内的有限消歧。`propose` 还要求同一任务身份的明确后继版本引用，保留案例、问题、回答与后继任务的来源；`no_change` 返回 None，不能伪造一次模型提交。

## 后继任务与验收边界

父任务和案例在探索开始前固定。探索候选和问题可以先于后继任务产生；回答形成新增目标后，应用使用预先固定的 probe→obligation 规则追加目标，固定新任务与计划版本，随后才请求最终提案。不能称为“全部候选产生前已固定新增目标”。

应用保留父声明、检查义务、绑定、来源和初始基准，不以新回答修改旧目标。后继准备重新核对案例、父任务和回答原字节；正式候选经已有 `preview → check → decide → apply`。父目标与新目标冲突时仍保留两者并拒绝提交。`no_change` 由应用检查原模型是否满足后继任务，评估结果与未提交事实分别返回。

未决不生成提案；不合法来源/字段、完整性或绑定失败抛 `ContractError`。回调执行失败继续传播，不偷偷更换检查器。完整意图建模、自然语言抽取、自动诊断证明、元模型迁移、LLM/Jev、持久化会话与研究比较不在本轮实现范围。
