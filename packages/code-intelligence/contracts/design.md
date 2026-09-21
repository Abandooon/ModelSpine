# 代码理解与演化目标合同

状态：draft，2026-09-21；运行模块仍 planned。[v0.1](v0.1/README.md) 是有限设计，研究方案责任见[框架中的 P4 方向](../../../docs/architecture.md#方向方法与可替换位置)。

拥有 ImplementationFact、恢复假设、TraceLink、SemanticDelta、覆盖记录和同步提案。输入为不可变代码/构建/运行制品引用、语言与分析范围、可选当前模型和追踪。消费者为编排、requirements、interaction、implementation；依赖 protocols/model-kernel 的公开边界。

## 操作与对象

- recover(code_ref,scope,configuration) → facts/hypotheses/uncovered/diagnostics；事实附 source/span/property/value/method/version/assumptions，静态与执行观测不能互相冒充。
- trace(facts,model_ref,prior_links) → links/conflicts/unmatched；链接带关系类型、两侧版本及支持证据，不能生成无依据全连接。
- diff(before,after,models,traces) → SemanticDelta；区分结构、行为、义务和映射改变；单独返回无法判定范围。
- propose_sync(delta,intent_ref,base) → ChangeProposal 或代码修改建议；事实与意图冲突不能自动以代码为真值解决。

恢复假设记录替代解释与待补证据；SemanticDelta 记录 before/after、changes、affected_obligations、uncovered、conflicts 和解释出处。无变化必须有覆盖依据，不以空列表替代解析失败。

## 演化和失败

代码版本、模型版本、语言/分析器版本共同绑定。旧位置失效后重新定位需保留依据；缺失或错误追踪是正常输入条件，不拒绝所有恢复，也不假装映射完整。unsupported 语言片段、error 工具失败、unknown 动态行为与 conflict 矛盾解释分开。

首个实现选一个明确语言子集与分析方式，不能只靠语言名宣称覆盖整个语言。人工代码与第三方代码仅提出修改建议，最终写入经 implementation 所有权边界。恢复与同步不承诺无损往返。

## 设计验收

A：从新制品获得可定位事实并生成追踪，无法定位的项不是事实。B：约束参数或调用/状态行为变化可被解释；布局/格式变化不冒充语义变化，无法判等为 unknown。C：追踪缺失/错误、别名、动态路径和与意图冲突均有反例。

模型 JSON diff、生成文件哈希和保护区只能作为辅助机制。研究分开固定补丁审查、恢复质量与多轮维护；公共内核失效正确不自动证明恢复出的依赖完整。
