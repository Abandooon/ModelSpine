# 生成合同 v0.1

范围说明：本页保留既有 v0.1 合同及工程样例；具体业务对象、角色、单位不构成通用默认或指定应用。完整目标见[设计合同](../design.md)，其新增内容为 draft，不能据此推定已有源码支持。

拥有 GenerationPlan、有限候选构造及修复进展判定，不拥有模型提交/应用文件；消费者 CLI/implementation。运行只依赖 protocols；assurance 是设计协作关系，预览由应用调用 kernel。

plan(CheckPlan, *, target, field) 列出此次单字段编辑的逐义务版本、支持片段、介入阶段、机制和剩余终验责任。只有匹配 target/field 且参数合法的 integer_range/equals 标记 construction；其他字段和不支持规则为 terminal-only 并列入 residual，匹配规则参数非法则明确拒绝。控制对应原 CheckPlan 中的义务 ID/version，并绑定完整计划哈希；计划是预定介入声明，不是已执行证据，也不校验快照中目标是否存在。

construct(snapshot,plan,proposal_id,target,field,value) 只构造 SetProperty，并校验真实目标、字段/值类型和提案 ID；支持的字段约束在构造中排除非法值。所有义务仍需独立终验，residual 仅列没有构造期控制的项，不能将其为空解读为终验完成。两类异质配置中的关系/行为规则均未加入本构造器。无状态写入、无自动重试/修复循环、无 LLM 后端。本次 Python API 要求显式 target/field，旧 plan(CheckPlan) 调用须更新；JSON v0.1 形状不变。

compare_reports(before,after) 提取 P0 纯比较：同计划/前提/工具/范围才可比，候选哈希可不同。新诊断、覆盖丢失、已评估转未知/错误/不适用均拒绝，必须严格改善。repair_progress 仅替换候选，不能授予提交/交付/业务批准。诊断数下降不能掩盖新错误。

A：合法阈值可构造；负数排除，手造负数仍被终验拒绝。B：旧许可不能借修复进展跨基准；订单/原域报告夹具用同机制。C：组件缺口保留剩余义务。共享版本变化同步 implementation；不声称约束任意 LLM，也不导入旧框架。
