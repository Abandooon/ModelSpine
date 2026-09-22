# 确定性有限自动机工程配置

这是有限行为语义样例，不指定业务应用。Machine 声明 `initial`、`alphabet`、`trace`；State 声明布尔 `accepting`；Transition 声明 `source/target/symbol`。只支持 parent 直接指向根的成员；当前根存在间接后代时明确 violated:not_flat_membership，不静默跳过嵌套转移或递归解释层次。其他独立根的成员不属于当前检查范围；端点必须属于本机的直接 State 成员。

支持的字母表为非空、不重复的 Unicode 码点字符串，每条转移消费一个码点；符号不是多字符 token，也不按字形合并组合码点。`deterministic_automaton` 检查端点、字母表和 `(source,symbol)` 唯一性；`finite_trace_acceptance` 在此基础上从 initial 实际遍历 trace，并判断最终状态是否接受。空输入串按初始状态的接受标记判断；未定义的转移或非接受终态均为 violated，不补造转移。

本配置没有 epsilon、guard、层级/并发状态、无限轨迹或时序逻辑。空/多字符转移符号不属于所声明有限格式，判 violated；其他义务 kind 保留 unknown。义务目标缺失、错误规则配置或虚假依赖完整声明为 error。它不是一般程序运行时或完整状态机语言。

从仓库根运行：

```text
python -B apps/boundary_examples.py --profile finite-automaton
```

原模型接受 `ab`。示例将第二条转移的符号改为 `a`，并把要验收的 trace 改为 `aa`，经共同的预览/检查/决定/提交入口保存；若只改转移而保留 `ab`，检查失败。行为由实际转移决定，不是比较状态字符串。

根列出所有成员依赖并设 `dependencies_complete=false`；转移列出端点依赖。v0.1 不能自动追踪将来新增成员，根声明完整时检查器返回 error；证据不得因当前检查通过而被称作 current。模型的 hypothesis/confirmed 仅表示样例假设，验收不证明研究比较优势。
