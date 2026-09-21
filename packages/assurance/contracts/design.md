# 保障能力目标合同

状态：draft，2026-09-21。当前 [v0.1](v0.1/README.md) 只检查有限设计字段；目标设计不能被解读为已实现一般形式化或独立保障。研究方法责任见[框架中的 P2 方向](../../../docs/architecture.md#方向方法与可替换位置)。

## 输入输出与责任

输入：已确认或显式待确认的意图、模型/代码引用、业务义务、目标范围、工具能力及独立参考证据。拥有 Obligation、Formalization、CheckPlan、支持说明；生产 protocols 唯一定义的 ValidationReport，不提交模型。消费者为 generation、component-reuse、平台编排；依赖 protocols/model-kernel。

Obligation 包含 id/version、意图出处、目标、前提、性质、适用范围和确认状态。Formalization 记录原义务、语言/片段、表达式、绑定、假设和未表达部分；不以编译成功表示忠实。CheckPlan 记录每项义务的执行器、适用性、资源预算和残余检查。

## 操作设计

- formalize(obligations,configuration) → formalizations/residuals；不支持片段保留义务，禁止生成恒真占位。
- compare_support(formalizations,checker_capabilities) → supported/unsupported/unknown 及依据；能力宣称与实际执行结果分开。
- plan(candidate_ref,obligations,support,budget) → CheckPlan；计划中的独立验收来源不能由生成器自行替换。
- check(candidate,plan,scope) → 逐义务报告/证据/收据；绑定实际候选、规则、工具、范围、前提；无模型写入。

分开四种问题：意图是否忠实、形式片段是否可执行、模型/代码绑定是否正确、候选是否符合义务。总体状态不能抹掉逐项 unknown/error。not_applicable 需要适用性依据，不得当作已检查通过。

## 失败与信任

缺目标/错版本是调用或绑定错误；求解超时/结果不确定保持 unknown 并记录原因；执行器故障为 error。不得自动换弱检查器或缩范围。外部报告必须绑定版本/哈希/执行来源，接收报告不是执行可信检查。

方法独立性来自真值建立与错误条件设计，不由“换一个模型/工具”自动保证。研究 oracle 与开发 checker 分离；生产报告附来源，论文实验还需实际验证错误相关性。

## 设计验收

A：可形式化义务有正反例，不能表达的部分留残余。B：改规则、绑定或工具使相应旧报告不再可直接复用；错候选报告拒绝。C：组件声明不能替代实际能力证据。合同与实现共同犯错仍需被独立任务真值揭露，或如实记录误放行。
