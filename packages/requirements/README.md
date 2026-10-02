# 需求澄清与模型细化

新增[有限审阅合同](contracts/review.md)：[review.py](src/modelspine_requirements/review.py)提供create_session/review_input/apply_action/review_ref，绑定外部候选原件、问题和独立审阅版本，记录回答、拒答、确认、完整候选提案、实例及显式提案采纳。采纳建立后继候选并保留旧审阅历史，旧确认和实例报告不移作新版本证据。纯状态处理不写文件；[应用入口](../../apps/model_review.py)负责显式本地目录保存/恢复和装配实例检查，与下文旧clarification进程内Session分开。actor只记录宿主提供的归属，结构合法和用户确认都不自动等于意图忠实。

[revision_request.py](src/modelspine_requirements/revision_request.py)提供确定性离线修订材料：保留原文和已记录回答/拒答的独立归属及候选/审阅版本。它不调用模型或创建后继候选；保存、导出与校验见[修订材料说明](../../docs/revision-request.md)。有限应用配置的共享合同由protocols持有，见[应用规格说明](../../docs/application-spec.md)。

新增[原文输入与领域候选合同](contracts/domain-modeling.md)：从 UTF-8 原文准备 ModelingRequest 和固定提示，解析带出处的概念、属性、关系/基数、规则及未决项，明确结构有效与语义未验收。当前 [CLI](../../apps/domain_modeling.py) 可 prepare/prompt/inspect；无需人工正确元模型。该新增入口没有语言传输或自动抽取，旧有限澄清范围如下。

已实现显式有限候选集上的结构化需求澄清：校验来源与基准，预览候选，通过实际行为差异选择布尔问题，记录绑定问题的回答，再为已消歧的解释生成 `ChangeProposal`。包本身只依赖 protocols 和标准库，无模型写权限。

状态、依赖和证据由 [module.json](module.json) 维护。实际字段、预算和版本语义见 [合同](contracts/v0.1/README.md)；[早期结构化样例](contracts/v0.1/examples.json)仍为设计材料，不是本轮输入格式。共享结构由 [protocols](../protocols/contracts/v0.1/README.md) 定义。

[运行入口](src/modelspine_requirements/__init__.py)；从仓库根运行 `python -B run_tests.py --package requirements` 验收本包，或运行 `python -B run_tests.py` 验收全部能力与集成。图可达性与有限自动机接受语义归适配器，后继任务构造与保存归应用，见[有限澄清闭环](../../docs/clarification.md)。

预算不足、缺证、无区分问题、拒答和冲突保留未决。候选只是调用方提供的有限列表，不证明所有可能解释已穷尽；本轮没有自然语言抽取、LLM/Jev 判断器、自动表示缺口证明或元模型迁移。`Session` 是可信进程内状态，不是跨进程授权凭证。

工程验收不是论文比较实验；未实现范围保持设计状态，未知不算通过。运行包不导入论文、实验或旧工作树。
