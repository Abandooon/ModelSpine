# 合同形式化与独立保障

已实现设计字段 integer_range/equals 检查，以及纯内存的固定任务准备与评估。任务来源、声明和映射合同见 [tasks.md](contracts/v0.1/tasks.md)，入口为 [tasks.py](src/modelspine_assurance/tasks.py)。有限图/自动机语义由外部 Checker 注入，不内置领域或论文条件。未知保持未知，映射与检查通过不证明意图忠实。

状态、依赖和证据由 [module.json](module.json) 维护。公开字段与错误/副作用/版本语义见 [合同](contracts/v0.1/README.md)，正反例见 [结构化样例](contracts/v0.1/examples.json)。共享结构只有 [protocols](../protocols/contracts/v0.1/README.md) 一处定义。

[运行入口](src/modelspine_assurance/__init__.py)；从仓库根运行 `python -B run_tests.py --package assurance` 验收本包，或运行 `python -B run_tests.py` 验收全部能力与集成。只用标准库；[验收记录](../../docs/validation.md)与[来源记录](../../docs/provenance.md)。

工程验收不是论文比较实验；未实现范围保持设计状态，未知不算通过。运行包不导入论文、实验或旧工作树。
