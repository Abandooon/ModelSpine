# 生成合同 v0.1

拥有 GenerationPlan、有限候选构造及修复进展判定，不拥有模型提交/应用文件；消费者 CLI/implementation。依赖 protocols/assurance；预览由应用调用 kernel。

plan(CheckPlan) 列出逐义务版本、支持片段、介入阶段、机制和剩余终验责任。construct(snapshot,plan,proposal_id,target,field,value) 只构造 SetProperty；支持的字段约束在构造中排除非法值，未知约束留 residual；终验仍独立执行。无状态写入、无自动重试/修复循环、无 LLM 后端。

compare_reports(before,after) 提取 P0 纯比较：同计划/前提/工具/范围才可比，候选哈希可不同。新诊断、覆盖丢失、已评估转未知/错误/不适用均拒绝，必须严格改善。repair_progress 仅替换候选，不能授予提交/交付/业务批准。诊断数下降不能掩盖新错误。

A：合法阈值可构造；负数排除，手造负数仍被终验拒绝。B：旧许可不能借修复进展跨基准；订单/原域报告夹具用同机制。C：组件缺口保留剩余义务。共享版本变化同步 implementation；不声称约束任意 LLM，也不导入旧框架。
