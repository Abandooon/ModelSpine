# 保障合同 v0.1

拥有义务、支持范围及检查实现；ValidationReport 唯一定义由 protocols 供应。消费者 generation/component-reuse/平台；kernel 注入 checker 不导入 assurance。

check(snapshot,plan,scope=None)→ValidationReport，无写副作用。CheckPlan 必填 id/version/rule_version/assumptions/obligations；Obligation 必填 id/version/kind/target/field/parameters。非空范围必须可解析；缺目标 error，未支持 kind unknown。首期支持 integer_range/equals，只检查设计字段，不代表运行应用批准。报告绑定候选/计划/范围/前提及真实工具版本；不修改意图。形式化/外部求解器/不适用证明仍设计态。

A：阈值范围、角色、失效策略逐项判定；规则合法不等于业务批准。B：新阈值重新检查，旧报告不能复用；unsupported 保留残余。C：恢复覆盖缺失不能 satisfied。未来工具失败 error/unknown，不更换弱检查器；当前只有离线解释器。共享严格编码，模型/义务版本变化重算，破坏性接口变更同步消费者。
