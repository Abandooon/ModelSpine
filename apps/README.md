# 平台应用

[model_review.py](model_review.py) 提供create_review/read_review/submit_action及create/show/act/demo命令：从原文请求和外部typed候选原字节建立有限审阅，在一个显式本地项目目录保存并核验版本链。候选原件与审阅版本分别绑定；answer/decline/confirm/完整候选编辑提案只追加用户动作，不自动采纳或修订。非法候选仍保留原件和诊断。它新增本地持久化，不改变下文clarification的进程内范围；该接口本身没有实例检查、认证服务或真实模型调用。接口、工程demo和失败责任见[给D的说明](../docs/model-review.md)。

[model_review_ui.py](model_review_ui.py) 提供有限前置审阅页面：`python -B -I apps/model_review_ui.py --project-dir "E:/absolute/existing-review-project"`，只服务一个显式目录和本机地址。interaction负责纯呈现，保存经model_review.py处理；回答、拒答、明确目标确认和完整候选提案不自动采纳或修订。启动、首次创建和恢复边界见[说明](../docs/model-review-ui.md)。完整Studio、实例审阅、应用生成和真实语言调用未实现。interaction由此app显式装配，bootstrap.PACKAGES仍为原五包。

[domain_modeling.py](domain_modeling.py) 是当前自然语言建模主线的首个合同消费者：prepare 接收原文及来源身份，prompt 导出固定指令，inspect 校验外部领域候选；已验收的有限增量提供 typed-prompt / typed-inspect 的来源绑定 typed 候选提示与检查，以及 check-project 对显式实例的有限检查。无损标量投影由 model-kernel 的 `domain_projection.to_scalar_metamodel` 提供，仅接受必填且不可空的纯标量定义，遇关系、规则、残余或可选/可空字段整项拒绝。详细语言及消费者合同仍为 draft。无需已有正确模型或编辑目录，结构检查不冒充语义正确；本CLI无实际语言模型调用、自动抽取、审阅 UI 或模型提交。命令与边界见[原文建模入口](../docs/domain-modeling.md)。

[bounded_generation.py](bounded_generation.py) 从固定 DAG 编辑空间构造候选：`python -B -I apps/bounded_generation.py`；`--case <card.json>` 加载显式任务卡，无需正确提案输入。`advance_construction` 从真实前序接受快照装配预先固定的后继任务，保留父目标并派生新版本引用。装配 generation 的有界步骤、领域控制、kernel 预览和原有任务验收。控制器与计划可同时显式注入；构造器、终验和保存规则固定，不接收参考答案。退出 0 为内存提交，1 为未保存，2 为输入/合同错误。范围见[有界构造合同](../docs/bounded-construction.md)。

用于平台工作台与 CLI 的真实应用入口。用户生成的软件项目放在独立仓库/工作区，以项目清单关联；实验实例由 studies 管理。

[candidate_batch.py](candidate_batch.py) 提供 `prepare_candidate_request`、`parse_candidate_selection` 和 `run_candidate_selection`，固定请求/来源/目录，严格校验原始选择载荷，再按返回顺序执行原目录选项。每次独立使用原base，空批次只表示backend_batch耗尽；真实后端传输与计费尚未接入。研究重放是其当前消费者，API细节与剩余项见[合同](../docs/candidate-backend-contract.md)。

[offline.py](offline.py) 串联四包和既有订单工程夹具，从仓库根运行 `python -B apps/offline.py`；`--threshold -1` 明确拒绝并退出 2。bootstrap.py 可按运行依赖选择当前仓库五包的 src，fixtures.py 负责示例输入；均不加载外部工作树。CLI 不生成应用仓库，不执行业务批准，不持久化；夹具不指定后续应用方向。

[平台入口](../README.md)

[boundary_examples.py](boundary_examples.py) 是公共基础边界复核入口：`python -B apps/boundary_examples.py --profile structural-graph` 或 `--profile finite-automaton`。它显式选择已知配置及对应 Checker，经过加载、预览、检查、决定和内存提交。`fixtures.load_case(path)` 是只加载三份配置文件的公开装配辅助，不自动发现检查器；缺文件/非法输入不会退回旧夹具。

两种配置是语义不同的工程样例，均不生成业务应用。图/自动机语义放在 adapters，有限标量元模型和事务放在能力包；真实支持与证据复用限制见[公共基础边界](../docs/foundation-boundaries.md)。

[task_acceptance.py](task_acceptance.py) 读取事先钉住的任务卡、原始 UTF-8 来源和显式提案，执行固定任务目标后才保存：

```text
python -B -I apps/task_acceptance.py --profile structural-graph
python -B -I apps/task_acceptance.py --profile finite-automaton
```

两者正例改名但保持元素身份与固定行为目标，返回 TaskAssessment、候选、已接受快照及 Commit。退出 0 表示本入口已保存，退出 1 表示未决/目标未满足而未保存，加载或合同错误退出 2；执行器异常传播，不切换检查器。保存只在内存，actor 由可信宿主指定，不提供用户认证服务。

`load_task(path, expected_task_ref, source_paths)` 只读取显式路径；工程卡路径限定在其目录内。预期 task_ref 由宿主在候选前选择，不能从候选提交的新文件临时推算后冒充原任务。无计划在输入身份校验后、构造内核前返回未检查；部分可检查目标仍保留报告，但必需意图未决阻止保存。详细接口见[实现交接](../docs/next-iteration.md)。

CLI 不加载参考验收。测试侧另对终候选/已保存版本评价，发生开发检查与参考分歧时分别保留事实，不反向修复或伪造回滚。Graph/FSM 选择只属于这两个工程示例，运行包的 TaskContract 没有永久 profile 枚举。

[clarification.py](clarification.py) 装配来源→有限解释预览→行为问题/固定回答→显式后继任务→最终提案与验收：`python -B -I apps/clarification.py --profile structural-graph` 或 `--profile finite-automaton`。来源、案例与回答按原字节固定；脚本回答仅为工程夹具。后继按固定探针和回答追加目标，保留父任务全部目标；原任务不被改写。退出 0 表示目标满足（可为无变更，须查看 commit），1 为未完成/目标未满足，2 为输入错误；未知异常传播。无交互 UI、持久化会话或自动 NLP，详见[当前边界](../docs/clarification.md)。
