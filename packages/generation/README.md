# 约束编译与生成修复

已实现有限离线切片：One SetProperty candidate construction with field controls; pure repair report regression gate; no LLM or repair loop。

状态、依赖和证据由 [module.json](module.json) 维护。公开字段与错误/副作用/版本语义见 [合同](contracts/v0.1/README.md)，正反例见 [结构化样例](contracts/v0.1/examples.json)。共享结构只有 [protocols](../protocols/contracts/v0.1/README.md) 一处定义。

[运行入口](src/modelspine_generation/__init__.py)；从工作区根运行 `python platform/run_tests.py` 或 `python platform/apps/offline.py`，只用标准库。[验收及来源记录](../../../artifacts/audits/modelspine/2026-09-21/README.md)。

工程验收不是论文比较实验；未实现范围保持设计状态，未知不算通过。运行包不导入论文、实验或旧工作树。
