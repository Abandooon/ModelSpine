# 适配器

[dag_construction.py](dag_construction.py) 从事先固定的边/端点空间提供 options、plan、control、build。移除旧边后在提案创建前检查是否引入回路；builder 同步端点与依赖，完整任务终验仍独立执行。只依赖 protocols、generation 和有限结构辅助，不导入 kernel/apps 或参考评价；[当前合同](../docs/bounded-construction.md)明确控制、构造与可信宿主的责任。

按实际需要加入 XML/XSD、代码技术栈、LLM/求解器、外部建模工具、既有需求建模原型、资产源等适配器。能力需有版本、支持范围、引用解析和错误状态；适配对象不决定通用框架，不预设应用。具体边界见[框架设计](../docs/architecture.md)。

[finite_models.py](finite_models.py) 提供两个显式 Checker：`check_structure` 验证有限有向结构图，`check_automaton` 验证确定性有限自动机并实际遍历有限输入串。二者仅依赖 protocols，由 [boundary_examples.py](../apps/boundary_examples.py) 装配到相同内核，未增加插件发现或自动后备。

配置及支持范围见[结构图](../domain-packs/structural-graph/README.md)与[有限自动机](../domain-packs/finite-automaton/README.md)。检查器扫描根的直接成员；v0.1 无法自动追踪将来新成员，因此根必须列出实际读取成员依赖并设 `dependencies_complete=false`。根声明完整时报告 error；证据初始适用性为 unknown，已有依赖发生变化可为 stale，不能宣称全图证据 current。

当前根的间接后代明确返回 violated:not_flat_membership，不静默忽略嵌套关系；其他独立根的成员不纳入当前范围。检查器直接收到包含循环或缺失 parent 的坏结构时返回 error，不沿坏引用无限遍历。

目标不存在为 error；目标存在但义务 kind 不支持为 unknown。支持的义务配置错误为 error；可判定的候选语义反例为 violated。检查失败不更换执行器或改变义务。

[task_checks.py](task_checks.py) 提供 `check_tasks(snapshot, plan, scope=None)`，工具身份为 `modelspine-task-checker/0.1.0`。保留三条旧有限规则，并增加两个从固定计划读取目标的规则：

- `graph_reachability` 使用 `field=root`，参数为 `source`、`destination` 字符串和 `expected_reachable` 布尔值。先验证当前支持的有效有向无环图，再按固定节点 ID 检查可达性，包含同一有效节点到自身的零长度路径。任务端点不属于本图为 error。
- `trace_acceptance` 使用 `field=initial`，参数为 `input` 字符串和 `expected_accept` 布尔值。先验证平坦、确定、依赖声明符合边界的有限自动机，再执行参数 input；不使用或替换候选的 `machine.trace`。输入超出声明字母表为 unknown；受支持输入遇到缺失转移或非接受终态是正常拒绝，可满足 expected_accept=false。

非法模型不能借负向期望得到 satisfied；参数类型或集合错误为 error。旧 `finite_trace_acceptance` 仍读取模型内 trace，超字母表仍按旧语义 violated，两者不混同。新旧消费者共享有限结构解析与执行辅助，没有向公共核心添加图/自动机分支；报告始终绑定实际原候选和原计划哈希。任务规则只判断已声明的有限目标，不证明意图完整或研究优势。

[平台入口](../README.md)

[clarification_checks.py](clarification_checks.py) 提供 `observe(snapshot, probe)` 与 `goal(probe, answer)`。前者复用有限模型解析，返回绑定候选/探针的 observed、unknown 或 error；非法模型不能成为 False。后者仅从事前固定的正向行为模板和布尔回答构造验收目标，不读取候选。适配器仅导入 protocols、requirements 与有限辅助；由 apps 注入通用澄清核心，不自动换检查器。支持边界与固定任务规则相同，不推导元模型表达不足。
