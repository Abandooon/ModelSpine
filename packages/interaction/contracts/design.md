# 任务交互目标合同

状态：draft，2026-09-21；运行模块仍 planned。已有 [v0.1](v0.1/README.md) 样例不能限定应用种类。研究设计责任见[框架中的 P3 方向](../../../docs/architecture.md#方向方法与可替换位置)。

输入：用户任务/角色、版本化模型与合同、差异/检查结果、implementation 的 CommandBinding 及可选视觉资产。拥有 TaskView、InteractionPlan、VisualAssetRef 与用户操作提案，不拥有模型或应用状态提交权。依赖 protocols/model-kernel/implementation 的公开合同。

## 两类交互及公开操作

业务界面面向应用任务，输出 CommandRequest；开发审查台面向模型/代码变化，输出 ChangeProposal 或审查决定。两者以 mode 和引用目标显式区分，不因复用组件混用权限或验收。

- project(task,model,contracts,mode) → TaskView，包含目标、命令、信息需求、条件/后果解释和未知范围。
- bind(view,command_bindings) → InteractionPlan，明确控件到类型化输入、结果、错误与并发字段的绑定。
- interpret(user_action,plan,versions) → CommandRequest/ChangeProposal/cancelled，不能自行提交。
- explain_change(delta,reports,task) → 带出处的后果解释；推断标为假设，不把不可判定解释为无影响。

TaskView 必含 id/version/mode/model_ref/task_ref/command_refs/explanations/unresolved/layout；语义内容与布局分离。VisualAssetRef 必含来源/用途/语义声明，视觉相似或文生图不能替代合同符合性。

## 操作与失败

序列化依输入类型、单位、精度规范进行，不能把所有控件值当字符串，也不全局固定金额表示。权限和前置条件由后端执行；UI 可解释禁用原因但不是授权依据。错误保留输入与诊断，成功确认后再改变交互状态；取消不提交。

绑定过时、业务版本冲突、缺权限、违反前置条件、检查未知与执行错误分别显示。版本冲突展示可重新确认的差异，不自动覆盖用户或模型状态。解释不能把检查通过称为用户业务许可。

## 设计验收

A：相同任务/合同可投影为不同布局，布局改变不修改业务语义。B：修改后果解释绑定版本，输入/状态/错误与后端一致，旧视图请求返回冲突。C：恢复假设、外部能力缺口和所有权冲突可见。工程验收与真人理解/操作研究分开；基础界面可实现而论文仍未获支持。
