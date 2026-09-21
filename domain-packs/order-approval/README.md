# 订单审批试点 0.1

人工可信设计模型，非自动需求恢复，不是客户需求认证。试点假设：固定 CNY、金额为整数分、最大 100000000 分；角色 manager；金额实际改变后批准失效；同金额写不增业务版本。阈值初始 100000 分。假设的 confirmed 只表示允许本试点采用，不把类别改成 intent 或 fact。

metamodel.json 定义 group/entity/policy/command/weather 五类及必需字段；model.json 绑定独立元模型版本和内容哈希。语义依赖为审批命令依赖规则与订单，天气同属根但无订单依赖；external-signal 的依赖明确不完整，用于 unknown 反例。

obligations.json 检查设计字段的范围、角色、币种与失效策略；它们不执行订单批准。业务订单版本与设计模型 revision 分开。contracts/examples.json 给出金额改变/重批/规则升级、CommandBinding、文件所有权冲突的合同样例；这些样例未运行应用后端、浏览器或文件物化，不算 S4 验收。

运行 `python platform/apps/offline.py`（从工作区根）；测试 `python platform/run_tests.py`。只需标准库；现有解释器见 workspace.local.json。CLI 是工作台工具，无应用仓库生成、无网络/LLM/持久化。非法 `--threshold -1` 返回退出码 2，未支持运行时义务明确 unknown。
