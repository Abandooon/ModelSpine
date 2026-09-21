# 组件复用合同 v0.1（reviewed，仅设计）

拥有 CapabilityProfile、CompatibilityReport、AdaptationProposal，依赖 protocols/assurance，消费者平台/implementation。inspect(ArtifactRef,scope)→能力事实/假设；match(profile,obligations)→兼容/缺口；plan_adoption(report,SnapshotRef)→采用/修改提案。只读源，不安装、不覆写、不直接提交模型。

Profile 必填 source/version/hash/operations/types/evidence_refs/assumptions/uncovered；Report 必填 profile_ref/obligation_versions/per_obligation_status/gaps；Adoption 必填 base/component_ref/model_proposal/adapter_files/ownership/migration_obligations。缺证据 unknown，协议不符 violated，工具失败 error；声明与实测分开，缺字段不能默认支持。无写重试语义。

A：审批组件对照权限/金额单位，同名不等价。B：规则升级重检版本化能力报告。C：外部金额用元、目标用分形成转换缺口，第三方文件不允许覆盖。共享严格版本/编码规则，破坏性变化同步消费者，不自动回退外部版本。首期无市场/检索/安装实现。
