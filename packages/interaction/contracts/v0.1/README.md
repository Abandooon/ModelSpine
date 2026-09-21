# 交互合同 v0.1（reviewed，仅设计）

范围说明：本页保留既有 v0.1 合同及工程样例；具体业务对象、角色、单位不构成通用默认或指定应用。完整目标见[设计合同](../design.md)，其新增内容为 draft，不能据此推定已有源码支持。

拥有 TaskView、InteractionPlan、VisualAssetRef/用户操作提案，不拥有执行或提交。输入任务/SnapshotRef/差异/报告及 implementation 的 CommandBinding；project→视图；bind→输入类型与命令；interpret→业务调用或 ChangeProposal。implementation 是公开合同供应依赖，不要求导入构建器。

TaskView 必填 id/model_ref/task/command_bindings/explanations/layout；Plan 必填 version/commands/unresolved；VisualAssetRef 必填 artifact_ref/purpose/semantic_claims（空表示无语义声明）。布局只改视图。金额字符串按固定币种/位数显式转整数分，多余小数/格式错 invalid；不能把字符串交 int 后端。后端权威验权，按钮禁用不算授权。版本冲突显示差异，不自动覆盖。

A：创建/批准视图显示残余；B：解释金额变化使批准失效，发送 expected_order_version，检查 passed 不显示订单批准；C：展示事实/假设/人工文件冲突，相似度不显示兼容通过。unknown/error/forbidden/conflict 原义保留，cancelled 不提交。视图投影只读，执行由平台/应用负责。共享/命令合同升版重新绑定；首期 CLI 不算浏览器实现。
