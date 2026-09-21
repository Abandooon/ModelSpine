# 需求合同 v0.1（reviewed，仅设计）

拥有 RequirementEvidence、Clarification、候选声明及 ModelProposal，无模型写权限。输入文档 ArtifactRef、片段 EvidenceRef、任务范围、SnapshotRef/答复；analyze→声明/未分类/冲突；clarify→版本化回答；propose→ChangeProposal。消费者平台/kernel，依赖 protocols/model-kernel；私有工作记录与已接受状态分开。

声明必填 id/category/confirmed/text/source_refs/scope；问题必填 id/version/question/alternatives/answer（null=未答）；提案必填共享 base/operations/intent_refs。不能表达返回 representation_gap，缺来源不能 fact。分析/提案只读；回答追加版本，同 ID 同内容幂等、不同 conflict；不改旧证据。

A：金额以分计是 intent，未答角色是 hypothesis；不能将试点默认写成真实需求。B：阈值/条件/范围变化构成语义差异，不能只比较名称。C：实现推断保留 fact/hypothesis，不覆盖意图。错误为 missing/unknown/unsupported/conflict；版本采用共享严格规则，破坏性变更同步消费者。当前人工可信领域包替代输入，不实现 NLP。
