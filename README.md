# ModelSpine

ModelSpine 研究以元模型为中心的人机协作软件开发，目标平台为 **ModelSpine Studio**。相对代码中心、规格中心和模型辅助方法的比较优势仍是待检验假设。

当前九模块已有合同设计；`protocols`、`model-kernel`、`assurance`、`generation` 提供有限离线模型变更实现，其他五模块为 planned。尚无完整无代码平台、应用运行时或研究比较结果。模块实际状态以各 `module.json` 和源码为准；目标合同 `contracts/design.md` 为 draft，不代表已有实现。

## 运行

使用 Python 3.10+，当前只依赖标准库，无安装步骤。从本仓库根执行：

```text
python -B run_tests.py
python -B apps/boundary_examples.py --profile structural-graph
python -B apps/boundary_examples.py --profile finite-automaton
python -B apps/offline.py
python -B apps/offline.py --threshold -1
```

两条 boundary_examples 命令通过显式适配检查器完成两类配置的加载、预览、检查、决定和模型提交；只解释各自有限语言，范围见[公共基础边界](docs/foundation-boundaries.md)。既有 offline CLI 执行字段构造与同一提交链，固定加载[订单工程夹具](domain-packs/order-approval/README.md)，不提供任意领域配置加载。最后一条为非法输入反例，预期退出码 2。所有入口均不指定未来应用试点。

## 框架与研究入口

- [九模块职责、解耦规则与方向实验入口](docs/architecture.md)
- [共享接口与当前支持范围](packages/protocols/contracts/v0.1/README.md)
- [两类异质配置与公共基础边界](docs/foundation-boundaries.md)
- [下一轮任务：版本化任务合同与固定目标验收（设计）](docs/next-iteration.md)
- [行为验收及结果边界](docs/validation.md)
- [机制来源与许可状态](docs/provenance.md)
- [适配器](adapters/README.md)、[领域包](domain-packs/README.md)、[平台应用](apps/README.md)
- [生命周期比较研究协议摘要](studies/lifecycle/protocol.md)

生产包仅通过声明的公开合同协作，不导入实验目录、论文或历史框架。实验编排放在 `studies/`，外部工具接入放在 `adapters/`，领域假设放在 `domain-packs/`。新增能力按真实消费者和验收推进，不为九个目录填空实现。

## 仓库边界与版本

本仓库保存当前代码、公开设计和测试；代码历史由 Git 提交管理，不在工作树存放往期代码目录或源码 ZIP。研究工作区中的私人稿件、回复信、参与者原始数据、本机配置和凭据不属于此仓库。Git 对象库用于版本管理，不属于重复维护的历史源码目录。

当前未声明项目许可证；来源许可与适配范围见来源记录，不能推定整个旧框架已集成或为平台赋予统一许可证。
