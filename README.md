# ModelSpine

ModelSpine 研究以元模型为中心的人机协作软件开发，目标平台为 **ModelSpine Studio**。相对代码中心、规格中心和模型辅助方法的比较优势仍是待检验假设。

当前九模块已有合同设计；`protocols`、`model-kernel`、`assurance`、`generation` 提供有限离线模型变更实现，`requirements` 增加显式有限解释上的结构化澄清及来源绑定的 typed 领域候选检查。本批有限交付已验收：有限领域语言及实例检查、必填且不可空的纯标量定义无损投影；投影遇关系、规则、残余或可选/可空字段整项拒绝。`interaction` 已提供有限审阅呈现，`implementation` 增加单一本机Web目标的生成制品运行与新目录更新；code-intelligence、component-reuse继续planned。尚无完整无代码平台或研究比较结果。模块实际状态以各 `module.json` 和源码为准；详细语言及消费者合同仍为 draft，不代表复杂执行器已实现。

版本化任务合同与固定目标检查已提供公共验收边界：共享信封归 protocols，来源与声明评估归 assurance，有限规则由适配器解释，apps 装配已有内核保存。当前[有限澄清闭环](docs/clarification.md)进一步将来源、解释、行为问题和回答连接到显式后继任务与模型提案。独立参考验收留在测试侧，和开发检查分别记录；此前固定任务切片的范围见[任务合同交接](docs/next-iteration.md)。

当前开发优先级是自然语言驱动的领域建模：**原文 → 概念、关系与约束候选 → 来源、未决项与澄清 → 领域元模型候选及可支持部分的校核**。当前已实现[原文请求、提示准备与外部候选检查](docs/domain-modeling.md)，不需要正确模型作为输入；新增 `typed-prompt`、`typed-inspect` 和有限 `check-project` 入口。新增[有界真实语言入口](docs/real-language.md)，按显式模型/端点/预算从原文获取候选并连接审阅保存；真实运行结果与失败见[验证记录](docs/validation.md)。回答驱动细化与独立语义验收尚未完成。现有有限澄清、任务绑定和报告边界可提供支撑；手写元模型中的标量字段、固定图编辑选项和脚本回答不等于已完成自然语言建模，也不提供完整领域语义。目标与当前能力的区别见[框架设计](docs/architecture.md)和[需求能力目标合同](packages/requirements/contracts/design.md)。

新增[有限审阅接口 model-review/0.1](docs/model-review.md)：外部候选原件、审阅动作和实例可在显式本地目录保存与恢复，检查拒绝的原件也可审阅；实例按声明的有限规则实际检查，合法完整提案须明确采纳才产生后继候选，旧确认和报告保留在历史中。[本地候选审阅 UI](docs/model-review-ui.md)提供相应编辑、检查、采纳和历史查看。回答还可导出[离线修订材料](docs/revision-request.md)，有来源的[有限应用规格](docs/application-spec.md)须另行配置及确认。这些功能不自动调用模型或完成语义验收，完整TaskView和Studio仍未实现。既有clarification的进程内会话与此本地保存入口分别维护。

基础产品目标是需求完善、领域建模/验证、代码前模型审阅、代码生成、运行交付和同项目修改的完整流程。自然语言建模是上游；更强语义保障与演化研究在该流程上增强，不以研究成功作为基础UI、生成和维护的前置。当前尚未贯通，来源组件须经实际适配与验收才能登记为可用。

当前无付费代码入口包括实例审阅/提案采纳、离线回答材料、显式应用规格，以及[本机模型编辑应用生成与更新](docs/local-web.md)。生成制品可独立启动并检查、保存和读取完整ProjectModel；它只覆盖声明的本地编辑任务，不生成任意业务应用，也不把手写工程输入当作真实语言链验收。

## 运行

使用 Python 3.10+，Python 代码只依赖标准库，无第三方 Python 包安装步骤。生成或更新本机 Web 制品还需要 PATH 中可用的 Git 和具有有效 HEAD 的平台 checkout，用于记录实际来源版本；已生成制品独立运行只需 Python 标准库。从本仓库根执行：

```text
python -B run_tests.py
python -B apps/boundary_examples.py --profile structural-graph
python -B apps/boundary_examples.py --profile finite-automaton
python -B apps/offline.py
python -B apps/offline.py --threshold -1
```

打开已保存审阅项目：`python -B -I apps/model_review_ui.py --project-dir "E:/absolute/existing-review-project"`，浏览器访问终端给出的本机地址。首次创建参数、保存失败和旧页冲突处理见[启动说明](docs/model-review-ui.md)；不自动生成候选。

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

有界构造入口：`python -B -I apps/bounded_generation.py`，或追加 `--case domain-packs/structural-graph/construction/multitask/fork-stage1/card.json` 加载显式输入。从固定端点空间构造真实边编辑，构造前排除成环选项，全部任务义务终验满足后才提交；输出保留每步结果与停止原因。有限后继由真实前序接受快照继续并保留父目标。详见[有界构造控制](docs/bounded-construction.md)及[三条件多任务先导](studies/construction/README.md)。[候选后端合同](docs/candidate-backend-contract.md)中的宿主请求绑定、严格选择和批次执行已提供；真实后端传输与 API 验收仍未接入。该合同保留为有限构造支线，后续接入按具体任务决定，不因已有宿主或配置可用而自动启动，也不代替当前自然语言建模主线。

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
