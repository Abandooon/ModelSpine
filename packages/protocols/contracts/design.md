# 共享协议目标合同

状态：draft，2026-09-21。用于全部已知能力的设计；现有 [v0.1](v0.1/README.md) 和源码才是已实现子集。本文的新对象/字段未实现，不要求旧解码器接受。全局责任见[框架设计](../../../docs/architecture.md)。

## 所有权与公开边界

供应所有能力包；自身不依赖能力包。负责共享引用、版本、交换信封和错误；领域概念、规则真值、存储与业务 payload 不在此定义。encode/decode/validate-reference 是拟议边界，运行名称以 v0.1 为准。

| 对象 | 必需语义 | 规则 |
|---|---|---|
| MetamodelRef | id、version、内容完整性绑定 | 不随项目模型 revision 变化；迁移显式执行 |
| SnapshotRef / ElementRef | project/model/revision/hash；element_id | 不以路径/名称代替身份，不隐式解析最新版本 |
| ArtifactRef / EvidenceRef | 身份、版本、哈希；位置、来源、形成方式 | 来源缺失不能伪造事实；确认状态不是来源类别 |
| ChangeProposal | id、base、有限操作、意图/证据、声明影响 | 声明影响仅提示；kernel 负责实际计算，未知保留 |
| ValidationReport | 候选、义务/计划、工具、范围、前提、逐项结果和残余 | satisfied/violated/unknown/not_applicable/error 分开 |
| AcceptanceDecision | 接受类型、主体、策略、基准、候选、报告与范围 | 修复进展、模型保存、业务允许、交付不能混用 |
| RunReceipt | 输入/输出、真实工具/模型、阶段、预算消耗、终态 | 原始响应与加工产物分开；未采集值以缺失原因表达 |

共享错误表达发生层与上下文：invalid/unsupported/not_found/conflict/forbidden 表示调用或提交问题；cancelled/timeout/error 表示执行终态，不能用单一“失败”覆盖所有含义。unknown 是知识/检查结果，不等同系统故障。

## 版本与失败

所有入口先解析版本与结构，再由相应能力检查语义。未知字段/类型不能被忽略后标为有效；可扩展 payload 必须有命名空间和支持声明。必填缺失、显式 null、已知空集合分别定义。集合的规范化与有序序列分开，哈希覆盖实际语义。

严格 v0.1 不承诺向前兼容。新增字段或状态先在目标合同给出消费者样例，经实际供应/消费后决定新版本；不把文档新增内容静默塞进 v0.1。任何升版不得改变旧运行的输入解释。

## 设计验收

- A：同一语义可由自然语言证据或已存在模型输入，不依赖业务名称。
- B：重命名保留 ID；旧修订引用、错元模型/候选绑定失败；confirmed 不改变 category。
- C：外部来源不可定位时保留缺失与 unknown；不能补成当前版本事实。
- 包间往返后所有版本与残余义务保持；结构合法不能被解释为业务正确。
