# 实现交付合同 v0.1（reviewed，仅设计）

拥有 CommandBinding、文件所有权、MigrationPlan、ApplicationBuild；消费 generation 候选，为 interaction 供应合同。materialize(candidate,file_manifest)→文件结果；build(model_ref,files,checks)→构建；package(build,policy)→交付或拒绝。设计状态归 kernel，订单状态归应用运行时，不重复生成修复编排。

CommandBinding 必填 id/contract_version/model_ref/input_type/output_type/permissions/preconditions/effects/errors/concurrency。样例 change_amount(order_id,amount_minor:int,expected_order_version:int)：editor，CNY，0..100000000 分，真实变化 order_version+1 并清空批准；同值写不增业务版本。approve(order_id,expected_order_version,rule_revision)：manager 且金额满足阈值；记录绑定订单版本/规则版本/actor。规则改变后旧批准不适用，即使金额没变。检查 satisfied 不产生业务批准。invalid/forbidden/conflict/violated 无部分状态。

文件项必填 path/owner(generated|human|third_party)/expected_old_hash/new_hash/model_ref。仅项目根内生成文件可写；路径越界、人工/第三方覆盖、生成文件现哈希不符均 conflict。不存在 expected_old_hash=null，已有必须精确哈希。整文件边界，先全量检查再事务物化；实现时须明确崩溃恢复，当前仅设计。

MigrationPlan 必填 from/to/schema_changes/data_obligations/rollback_limits；Build 必填 id/model_ref/file_refs/commands/reports/residual/status。模型提交与构建分事务，构建失败保留失败记录；交付要求必需范围全部 satisfied，checked-save 不足以交付。

A：命令/文件/终验后交付，缺验收拒绝。B：规则升级迁移重建并复核旧批准，旧订单版本 conflict。C：只生成组件适配文件，不覆盖第三方。合同/设计/业务版本独立，破坏性升级通知 interaction；首期无应用后端/构建/部署。
