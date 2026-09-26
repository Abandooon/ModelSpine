# 需求能力目标合同

状态：目标合同仍为 draft；2026-09-26 已实现[有限 v0.1 切片](v0.1/README.md)，实际范围为结构化来源、显式解释列表、布尔行为提问、绑定回答及提案装配。以下完整分析/诊断操作仍是设计，不能据此推定全部已有实现。方法与论文验收责任见[框架中的 P1 方向](../../../docs/architecture.md#方向方法与可替换位置)。

当前切片通过应用保留父任务目标并追加明确回答对应的后继任务；来源、问题、回答和候选分别绑定版本与哈希。它不证明解释列表已穷尽，不自动区分 mapping_error/model_gap/representation_gap，也不把有限收敛视为意图忠实证明；实际预算、unknown、no_change 与停止条件以 v0.1 合同为准。完整诊断、支持/反对证据推理和元模型扩展仍需独立实现与验收。

## 状态与数据

拥有需求证据、未决问题、答复和候选声明；无已接受模型写权。输入为版本化原文/实例、任务目标、可选当前模型/元模型配置及现有事实。输出供应平台编排、kernel、assurance；依赖 protocols/model-kernel 的公开合同。

RequirementEvidence 必须包含原文引用、位置、原始版本、形成方式和证据类别。Claim 包含 id/category/confirmation/text/scope/source_refs；模型候选保留支持与反对证据。Clarification 包含 question_id/version、触发差异、可区分选项、回答及预算；未答与拒答不等同否定。

## 操作设计

- analyze(inputs,scope,configuration) → claims/unclassified/conflicts/diagnoses；只读分析，不从代码事实推定用户意图。
- diagnose(claims,model,tasks) → mapping_error/model_gap/representation_gap/intent_undetermined/unknown 及可检查依据；证据不足时不强制二分类。
- clarify(diagnoses,budget) → 有序问题及预期区分的候选；预算用尽保留未决项，不合成用户回答。
- record_answer(question_ref,answer,actor) → 新版本答复；过时问题或冲突回答显式处理，原回答保留。
- propose/refine(claims,answers,base) → 模型 ChangeProposal 或元模型扩展建议；前者交 kernel，后者先检查消费者/迁移范围，不能自动扩语言后宣称需求已满足。

诊断与提案记录来源、方法版本和当前范围，不把启发式打分称校准概率。required、modality、condition、scope、约束参数等均可能改变语义，不能仅按名称匹配；无法判等标为待复核。

## 版本、失败与验收

文档/问题/回答/模型分别绑定版本；相同记录 ID 内容改变为 conflict。来源不能读取为 error，语言/表达不支持为 unsupported，解释缺证为 unknown。错误、缺失和未分类都进入输出分母。

A：相同原文可保留多个候选解释，并由有区分力的问题收敛；无依据概念不得自动确认。B：新需求区分原遗漏、新形成目标和外部变化；细化不能破坏既有任务。C：外部实现事实与期望不符时报告分歧，不能以现状覆盖意图。

独立留出任务用于检验充分性，不能拿片段覆盖率当需求正确率。通用内核建设属于上游工程条件，不是本模块或 P1 的研究结果。
