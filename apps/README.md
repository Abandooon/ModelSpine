# 平台应用

用于平台工作台与 CLI 的真实应用入口。用户生成的软件项目放在独立仓库/工作区，以项目清单关联；实验实例由 studies 管理。

[offline.py](offline.py) 串联四包和既有订单工程夹具，从仓库根运行 `python -B apps/offline.py`；`--threshold -1` 明确拒绝并退出 2。bootstrap.py 连接当前仓库四包的 src，fixtures.py 负责示例输入；均不加载外部工作树。CLI 不生成应用仓库，不执行业务批准，不持久化；夹具不指定后续应用方向。

[平台入口](../README.md)

[boundary_examples.py](boundary_examples.py) 是公共基础边界复核入口：`python -B apps/boundary_examples.py --profile structural-graph` 或 `--profile finite-automaton`。它显式选择已知配置及对应 Checker，经过加载、预览、检查、决定和内存提交。`fixtures.load_case(path)` 是只加载三份配置文件的公开装配辅助，不自动发现检查器；缺文件/非法输入不会退回旧夹具。

两种配置是语义不同的工程样例，均不生成业务应用。图/自动机语义放在 adapters，有限标量元模型和事务放在能力包；真实支持与证据复用限制见[公共基础边界](../docs/foundation-boundaries.md)。
