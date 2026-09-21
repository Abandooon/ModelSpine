# ModelSpine

ModelSpine 研究以元模型为中心的人机协作软件开发，目标平台为 **ModelSpine Studio**。相对代码中心、规格中心和模型辅助方法的比较优势仍是待检验假设。

当前九模块已有合同设计；`protocols`、`model-kernel`、`assurance`、`generation` 提供有限离线模型变更实现，其他五模块为 planned。尚无完整无代码平台、应用运行时或研究比较结果。模块实际状态以各 `module.json` 和源码为准；目标合同 `contracts/design.md` 为 draft，不代表已有实现。

## 运行

使用 Python 3.10+，当前只依赖标准库，无安装步骤。从本仓库根执行：

```text
python -B run_tests.py
python -B apps/offline.py
python -B apps/offline.py --threshold -1
```

最后一条命令用于验证非法输入，预期退出码为 2。CLI 执行候选构造、预览、检查、决定、模型提交和证据适用性判断，当前加载[既有订单工程夹具](domain-packs/order-approval/README.md)。该夹具用于回归，不指定未来应用试点；CLI 尚不提供任意领域配置加载。

## 框架与研究入口

- [九模块职责、解耦规则与方向实验入口](docs/architecture.md)
- [共享接口与当前支持范围](packages/protocols/contracts/v0.1/README.md)
- [行为验收及结果边界](docs/validation.md)
- [机制来源与许可状态](docs/provenance.md)
- [适配器](adapters/README.md)、[领域包](domain-packs/README.md)、[平台应用](apps/README.md)
- [生命周期比较研究协议摘要](studies/lifecycle/protocol.md)

生产包仅通过声明的公开合同协作，不导入实验目录、论文或历史框架。实验编排放在 `studies/`，外部工具接入放在 `adapters/`，领域假设放在 `domain-packs/`。新增能力按真实消费者和验收推进，不为九个目录填空实现。

## 仓库边界与版本

本仓库保存当前代码、公开设计和测试；代码历史由 Git 提交管理，不在工作树存放往期代码目录或源码 ZIP。研究工作区中的私人稿件、回复信、参与者原始数据、本机配置和凭据不属于此仓库。Git 对象库用于版本管理，不属于重复维护的历史源码目录。

当前未声明项目许可证；来源许可与适配范围见来源记录，不能推定整个旧框架已集成或为平台赋予统一许可证。
