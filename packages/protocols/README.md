# 共享协议与稳定引用

已实现有限离线切片：严格不可变 v0.1 JSON、标量字段元模型、身份/版本/哈希绑定，以及同步 Checker 接口。包版本为 0.1.1-experimental，JSON api_version 仍为 0.1。

状态、依赖和证据由 [module.json](module.json) 维护。公开字段与错误/副作用/版本语义见 [合同](contracts/v0.1/README.md)，正反例见 [结构化样例](contracts/v0.1/examples.json)。共享结构只有 [protocols](../protocols/contracts/v0.1/README.md) 一处定义。

[运行入口](src/modelspine_protocols/__init__.py)；从仓库根运行 `python -B run_tests.py --package protocols` 验收本包，或运行 `python -B run_tests.py` 验收全部能力与集成。只用标准库；[验收记录](../../docs/validation.md)与[来源记录](../../docs/provenance.md)。

工程验收不是论文比较实验；未实现范围保持设计状态，未知不算通过。运行包不导入论文、实验或旧工作树。
