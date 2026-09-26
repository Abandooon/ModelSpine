# 平台应用

[bounded_generation.py](bounded_generation.py) 从固定 DAG 编辑空间构造候选：`python -B -I apps/bounded_generation.py`；`--case <card.json>` 加载显式任务卡，无需正确提案输入。`advance_construction` 从真实前序接受快照装配预先固定的后继任务，保留父目标并派生新版本引用。装配 generation 的有界步骤、领域控制、kernel 预览和原有任务验收。控制器与计划可同时显式注入；构造器、终验和保存规则固定，不接收参考答案。退出 0 为内存提交，1 为未保存，2 为输入/合同错误。范围见[有界构造合同](../docs/bounded-construction.md)。

用于平台工作台与 CLI 的真实应用入口。用户生成的软件项目放在独立仓库/工作区，以项目清单关联；实验实例由 studies 管理。

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
