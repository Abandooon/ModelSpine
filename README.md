# ModelSpine

ModelSpine 研究以元模型为中心的人机协作软件开发，目标平台为 **ModelSpine Studio**。相对代码中心、规格中心和模型辅助方法的比较优势仍是待检验假设。

当前九模块已有合同设计；`protocols`、`model-kernel`、`assurance`、`generation` 提供有限离线模型变更实现，`requirements` 增加显式有限解释上的结构化澄清，其他四模块为 planned。尚无完整无代码平台、应用运行时或研究比较结果。模块实际状态以各 `module.json` 和源码为准；目标合同 `contracts/design.md` 为 draft，不代表已有实现。

版本化任务合同与固定目标检查已提供公共验收边界：共享信封归 protocols，来源与声明评估归 assurance，有限规则由适配器解释，apps 装配已有内核保存。当前[有限澄清闭环](docs/clarification.md)进一步将来源、解释、行为问题和回答连接到显式后继任务与模型提案。独立参考验收留在测试侧，和开发检查分别记录；此前固定任务切片的范围见[任务合同交接](docs/next-iteration.md)。

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

固定任务入口：

```text
python -B apps/task_acceptance.py --profile structural-graph
python -B apps/task_acceptance.py --profile finite-automaton
```

任务输入来自预先固定的合同和来源；自动机任务使用合同中的固定输入串，不以候选模型的 `trace` 替换目标。输出分别保留任务评估与模型提交；无计划、必需意图未决或开发检查未全满足时不提交。该 CLI 不执行参考验收，也不声称完整用户意图已获证明。

有限澄清入口：

```text
python -B apps/clarification.py --profile structural-graph
python -B apps/clarification.py --profile finite-automaton
```

该入口只处理可信结构化来源、显式候选和脚本回答。回答收敛后追加目标并固定后继任务，再构造正式提案；保留全部父目标，未决或开发检查不满足时不提交。`no_change` 只评估原模型，不伪造提交。没有自然语言抽取、全语言解释穷尽或意图忠实性证明。

## 框架与研究入口

有界构造入口：`python -B -I apps/bounded_generation.py`。从固定端点空间构造真实边编辑，构造前排除成环选项，全部任务义务终验满足后才提交；输出保留每步结果与停止原因。详见[有界构造控制](docs/bounded-construction.md)。

- [九模块职责、解耦规则与方向实验入口](docs/architecture.md)
- [共享接口与当前支持范围](packages/protocols/contracts/v0.1/README.md)
- [两类异质配置与公共基础边界](docs/foundation-boundaries.md)
- [本轮实现交接：版本化任务合同与固定目标验收](docs/next-iteration.md)
- [有限解释、澄清回答与后继任务](docs/clarification.md)
- [有界构造与固定任务接受](docs/bounded-construction.md)
- [任务准备与评估合同](packages/assurance/contracts/v0.1/tasks.md)
- [行为验收及结果边界](docs/validation.md)
- [机制来源与许可状态](docs/provenance.md)
- [适配器](adapters/README.md)、[领域包](domain-packs/README.md)、[平台应用](apps/README.md)
- [生命周期比较研究协议摘要](studies/lifecycle/protocol.md)

生产包仅通过声明的公开合同协作，不导入实验目录、论文或历史框架。实验编排放在 `studies/`，外部工具接入放在 `adapters/`，领域假设放在 `domain-packs/`。新增能力按真实消费者和验收推进，不为九个目录填空实现。

## 仓库边界与版本

本仓库保存当前代码、公开设计和测试；代码历史由 Git 提交管理，不在工作树存放往期代码目录或源码 ZIP。研究工作区中的私人稿件、回复信、参与者原始数据、本机配置和凭据不属于此仓库。Git 对象库用于版本管理，不属于重复维护的历史源码目录。

当前未声明项目许可证；来源许可与适配范围见来源记录，不能推定整个旧框架已集成或为平台赋予统一许可证。
