# 保障合同 v0.1

范围说明：本页保留既有 v0.1 合同及工程样例；具体业务对象、角色、单位不构成通用默认或指定应用。完整目标见[设计合同](../design.md)，其新增内容为 draft，不能据此推定已有源码支持。

拥有义务、支持范围及检查实现；ValidationReport 唯一定义由 protocols 供应。消费者 generation/component-reuse/平台；kernel 注入 checker 不导入 assurance。

check(snapshot,plan,scope=None)→ValidationReport，无写副作用。CheckPlan 必填 id/version/rule_version/assumptions/obligations；Obligation 必填 id/version/kind/target/field/parameters。非空范围必须可解析；缺目标 error，未支持 kind unknown。首期支持 integer_range/equals，只检查设计字段，不代表运行应用批准。报告绑定候选/计划/范围/前提及真实工具版本；不修改意图。形式化/外部求解器/不适用证明仍设计态。

当前 `check` 满足 protocols.Checker 的同步调用合同，应用或实验编排可显式选择其他实现。缺失目标始终 error，优先于未知 kind；目标存在但 kind 未支持时 unknown，不推断未知规则的 field 语义。kernel 核对返回绑定和覆盖，不导入 assurance，也不会因替代检查器失败自动退回本实现。方法语义、读取依赖完整性及独立真值仍由相应实现和研究设计负责。结构图与有限自动机检查实现位于[显式适配器](../../../../adapters/README.md)，不是本包新增的内置规则。

A：阈值范围、角色、失效策略逐项判定；规则合法不等于业务批准。B：新阈值重新检查，旧报告不能复用；unsupported 保留残余。C：恢复覆盖缺失不能 satisfied。未来工具失败 error/unknown，不更换弱检查器；当前只有离线解释器。共享严格编码，模型/义务版本变化重算，破坏性接口变更同步消费者。

新增独立任务信封的准备/评估接口见 [tasks.md](tasks.md)，不改变本页原字段检查 API。
