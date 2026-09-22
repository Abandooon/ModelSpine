# 适配器

按实际需要加入 XML/XSD、代码技术栈、LLM/求解器、外部建模工具、既有需求建模原型、资产源等适配器。能力需有版本、支持范围、引用解析和错误状态；适配对象不决定通用框架，不预设应用。具体边界见[框架设计](../docs/architecture.md)。

[finite_models.py](finite_models.py) 提供两个显式 Checker：`check_structure` 验证有限有向结构图，`check_automaton` 验证确定性有限自动机并实际遍历有限输入串。二者仅依赖 protocols，由 [boundary_examples.py](../apps/boundary_examples.py) 装配到相同内核，未增加插件发现或自动后备。

配置及支持范围见[结构图](../domain-packs/structural-graph/README.md)与[有限自动机](../domain-packs/finite-automaton/README.md)。检查器扫描根的直接成员；v0.1 无法自动追踪将来新成员，因此根必须列出实际读取成员依赖并设 `dependencies_complete=false`。根声明完整时报告 error；证据初始适用性为 unknown，已有依赖发生变化可为 stale，不能宣称全图证据 current。

当前根的间接后代明确返回 violated:not_flat_membership，不静默忽略嵌套关系；其他独立根的成员不纳入当前范围。检查器直接收到包含循环或缺失 parent 的坏结构时返回 error，不沿坏引用无限遍历。

目标不存在为 error；目标存在但义务 kind 不支持为 unknown。支持的义务配置错误为 error；可判定的候选语义反例为 violated。检查失败不更换执行器或改变义务。

[平台入口](../README.md)
