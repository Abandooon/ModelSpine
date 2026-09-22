# 有向结构图工程配置

这是通用边界的有限工程样例，不指定业务应用。Graph 的 `root` 指向本图一个 Node；Edge 的 `source/target` 指向本图 Node。只支持 parent 直接指向根的节点和边；当前根存在间接后代时明确 violated:not_flat_membership，不静默跳过嵌套边或递归解释层次。其他独立根的成员不属于当前检查范围。`directed_acyclic_graph` 检查端点存在及类型、起始节点和无环性，不检查全图可达、一般关系代数或跨模型引用。

结构引用以标量 ID 表达，由显式适配器解释；公共协议仍只有标量字段，不因此升级为任意关系语言。根列出所有成员依赖并标为不完整，边列出端点依赖。由于成员选择不能追踪将来新增元素，整图证据只能 unknown 或在已读内容改变后 stale。

从仓库根运行：

```text
python -B apps/boundary_examples.py --profile structural-graph
```

示例加载三份 JSON，经同一 ModelKernel 预览、检查、决定和提交，将 `node-b → node-c` 改为 `node-a → node-c`，同时更新边依赖。已知悬空端点、端点类型错误或环为 violated；根目标缺失、错误规则配置或虚假完整声明为 error；未支持义务 kind 为 unknown。失败不提交。

模型中的 hypothesis/confirmed 表示本工程样例显式采用的假设，不表示真实用户确认或来源恢复。JSON 及代码支持范围都不构成研究优势结论。

固定目标版本见 [任务合同](tasks/task.json)及[任务卡](tasks/card.json)。公开 [source.txt](tasks/source.txt)由工程任务作者确认；卡片钉住原始字节与来源，不从候选自带输入重建目标。运行 `python -B -I apps/task_acceptance.py --profile structural-graph`；此正例改名保持身份，行为反例由集成验收另测。
