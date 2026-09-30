# 任务界面与用户审查

保留原 S1 可评审合同与三场景推演；现提供[有限候选审阅 UI](../../docs/model-review-ui.md)，从 A 的本地审阅视图呈现术语、字段、关系、规则、问题与诊断，并提交答复、拒答、明确目标确认和完整候选提案。运行边界见[审阅呈现合同](contracts/review.md)。

当前不支持实例查看、提案采纳、自动修订/新候选生成或应用运行；旧交互设计并未全部实现。本批工程交付不表示 F1/F2 完成。

状态、依赖和证据由 [module.json](module.json) 维护。公开字段与错误/副作用/版本语义见 [合同](contracts/v0.1/README.md)，正反例见 [结构化样例](contracts/v0.1/examples.json)。共享结构只有 [protocols](../protocols/contracts/v0.1/README.md) 一处定义。

工程验收不是论文比较实验；未实现范围保持设计状态，未知不算通过。运行包不导入论文、实验或旧工作树。
