# 代码理解合同 v0.1（reviewed，仅设计）

拥有 ImplementationFact、TraceLink、SemanticDelta/恢复假设；输入代码 ArtifactRef、覆盖范围、SnapshotRef/既有映射。recover→事实/假设/uncovered；trace→源位置到 ElementRef；diff(before,after)→变化/冲突/ChangeProposal 建议。消费者 requirements/implementation/interaction 经平台编排，合同依赖 protocols/model-kernel。

Fact 必填 id/source/span/property/value/assumptions；Trace 必填 code_ref/model_ref/relation/evidence_refs；Delta 必填 before/after/changes/uncovered/conflicts。未知值 null+原因，不当空值/无变化。只读输入并产制品，无自动反向写回；同输入哈希/工具版本可复核，不承诺一般往返。unsupported 语言、error 解析、unknown 覆盖、conflict 漂移均保留。

A：构建后追踪文件，缺源不合成事实。B：约束参数变化进入 delta，手写修改交所有权检查。C：硬编码阈值为 fact，是否业务期望另问，动态路径 uncovered。引用严格绑定版本，破坏性合同变化同步消费者；首期不实现恢复器。
