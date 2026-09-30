# 框架、模块与研究扩展

ModelSpine 是元模型中心的软件开发框架，ModelSpine Studio 是目标平台。平台能力、论文方法和实验结论分别管理；公共内核服务所有方向，不等同于需求方向的研究贡献。比较优势尚未得到本平台实验支持。

完整基础产品包含自然语言需求完善、领域元模型与验证器、代码生成前的用户理解完善、应用生成运行及同项目维护。研究增强在基础流程中逐项接入；成熟建模/生成/执行组件可以适配，来源能力与本平台已验证能力分别登记。阶段性交付先贯通一个目标，再扩大桌面和语义支持，不用局部语义工具替代产品。

## 当前开发重点

当前优先推进自然语言驱动的领域建模：版本化原文 → 概念、关系与约束候选 → 来源、未决项与澄清 → 领域元模型候选及可支持部分的校核。已提供[原文输入与领域候选合同消费者](domain-modeling.md)，包括请求、固定提示、外部候选结构/引用检查，以及来源绑定的 typed 候选检查和有限 check-project；另有[有限前置候选审阅 UI](model-review-ui.md)。新增[有界真实语言传输](real-language.md)和原文候选装配；实际生成/失败与工程验收分别记录，自动语义忠实性验证及完整Studio尚未实现。

既有 requirements 有限解释切片预先接收解释及其模型操作，所有候选使用同一个既定元模型，再以固定布尔探针区分。它可以提供来源绑定、回答留痕和未决停止的实现参考；新增 typed 候选另用领域定义合同承载。protocols 的旧 `Metamodel`/`KindSpec`/`FieldSpec` 定义有限标量结构；新增 `domain_language` 的 finite-domain/0.1 支持实体、三标量、二元关系、双向基数和有限纯表达式，由 apps/domain_checks.py 执行实例检查。详细语言及消费者合同仍为 draft，复杂执行器未实现；旧图配置与自动机行为仍由各自适配器解释。

自然语言建模的候选与解释仍归 requirements，来源完整性与已支持部分的检查可消费 protocols 和 assurance；apps 装配可审查流程。新的候选产物先按实际消费者设计，不强塞入现有同元模型 `ChangeProposal`，也不提前实现通用元模型迁移。模型提交继续由 kernel 负责，候选草案、人工确认、形式检查和已接受模型分别记录。

[有限审阅接口](model-review.md)已提供独立候选/审阅身份及四种追加动作：protocols.review定义封闭动作，requirements.review负责纯审阅转换与重放，apps/model_review.py在显式本地目录互斥保存、恢复并拒绝旧版本/损坏。原件检查拒绝仍可审阅，propose_edit只保存待采纳完整候选；没有实例输入或自动修订。apps/model_review_ui.py通过本机HTTP装配该保存入口，interaction只提供纯文本/表格投影和页面资源，不拥有审阅状态。该本地保存不改变旧clarification会话只在进程内的边界，也不构成已接受模型提交。

有界 DAG 构造、三条件记录和候选批次重放保留为保障机制与比较方法的工程支撑。[候选后端合同](candidate-backend-contract.md)是这条支线的接入设计，当前主线不要求先完成其外部 API。具体支线按任务启动，目录或可运行入口的存在不决定下一优先级。

## 九模块的职责

| 模块 | 拥有的状态或产物 | 公开边界及当前范围 |
|---|---|---|
| [protocols](../packages/protocols/contracts/design.md) | 共享身份、版本、交换值对象、错误 | 已实现严格 v0.1 JSON、有限标量元模型、任务信封与公共报告校验、finite-domain/0.1值对象及静态检查；新增model-review/0.1动作信封，不持有项目状态 |
| [model-kernel](../packages/model-kernel/contracts/design.md) | 已接受快照、决定、提交、证据适用性 | 已实现单实例内存事务、六种操作和依赖影响；新增必填且不可空的纯标量定义只读无损投影，拒绝关系/规则/残余及可选/可空字段；无持久化或跨进程事务 |
| [requirements](../packages/requirements/contracts/design.md) | 需求证据、问题、答复、诊断、候选 | 已实现显式有限解释澄清、原文/typed候选提示与检查；新增有限审阅会话及用户动作，文件保存归apps；无自动抽取、自动修订或直接模型写权，通用诊断仍为设计 |
| [assurance](../packages/assurance/contracts/design.md) | 义务、形式化、检查计划、逐项报告 | 已实现设计字段 integer_range/equals；已实现固定任务准备与评估，一般形式化和外部求解器仍属设计 |
| [generation](../packages/generation/contracts/design.md) | 生成计划、候选、修复建议、运行轨迹 | 已实现单字段控制、有界选项构造/终验记录和纯报告比较；DAG 语义留在适配器，无 LLM 或完整修复循环 |
| [implementation](../packages/implementation/contracts/design.md) | CommandBinding、文件计划、构建、迁移计划 | planned；承担文件所有权、业务绑定和交付边界 |
| [interaction](../packages/interaction/contracts/design.md) | TaskView、交互计划、用户请求 | 已实现有限前置审阅投影与页面资源；完整TaskView/InteractionPlan仍为设计，业务界面与开发审查台分开，无模型或业务授权权力 |
| [code-intelligence](../packages/code-intelligence/contracts/design.md) | 实现事实、恢复假设、追踪、语义差异 | planned；必须记录来源和未覆盖部分，不能以代码事实覆盖意图 |
| [component-reuse](../packages/component-reuse/contracts/design.md) | 外部能力说明、兼容性结果、适配建议 | planned；相似或来源声明不等于行为兼容 |

`contracts/design.md` 描述目标，`contracts/v0.1` 描述当前合同或有限设计；成熟度与实现状态由各 module.json 标明。目标中的新字段不自动进入严格 v0.1，也不承诺任意语言、任意领域或完整应用生成。

## 依赖与装配

当前运行依赖是 `model-kernel → protocols`、`assurance → protocols`、`generation → protocols`、`requirements → protocols`；protocols 不依赖其他能力包；interaction的有限呈现仅依赖标准库。其余三模块没有运行实现。module.json 的 `runtime_dependencies` 表达这层实际依赖；planned 模块为 null，不能将 null 解读为已实现独立运行。

`depends_on` 保留目标设计所消费的能力合同：requirements/code-intelligence 消费 kernel，assurance 消费 kernel 的模型边界，generation/component-reuse 消费 assurance 的公开义务与报告，implementation 消费 generation，interaction 消费 kernel 与 implementation 的 CommandBinding。设计依赖不授权直接导入另一包内部实现。

模块 manifest 的文件引用相对所在模块目录；`reference_sources.asset_id` 和 `review_targets` 是来源、研究工作区联动的逻辑标识，不是 Python 包或运行依赖。公共来源、验证入口均在本仓库内。

apps/language_modeling.py以固定原文/提示/请求参数装配adapters/language_response.py的单一无状态Responses传输和既有typed检查、审阅存储；配置与预算由显式宿主提供，不进入requirements/protocols的runtime依赖。真实调用收据与既有generation_provenance=not_verified分别保留，调用成功不等于语义忠实。

apps 负责装配当前能力；studies 可装配替代方法、检查器、条件和记录器。运行包不能反向导入 apps/studies/tests/research。适配器实现公开合同，按调用显式选择；失败不自动换后端。尚无实际消费者的扩展保持设计，不预建插件注册中心、运行框架或空包实现。

当前真实检查器入口是 `protocols.Checker(snapshot, plan, scope=None) -> ValidationReport` 的同步调用合同。kernel 核对返回报告结构、候选/计划/范围/前提绑定及义务覆盖，执行器异常不被转成成功。替换检查器不需修改 kernel 的能力依赖。模型依赖必须覆盖检查器实际读取的数据；`dependencies_complete` 是可信声明，当前不自动追踪读集，报告绑定校验不能证明依赖完整或语义正确。

本轮将既有报告完整性校验归入 `protocols.validate_report(report, snapshot, plan, scope)`，供 kernel 和 assurance 共用。`select_scope(plan, scope=None)` 规范化计划全部目标或合法非空子集；校验调用方必须显式传入预期范围，不能信任报告自行缩小范围。共同校验保持结构错误与错绑定的拒绝行为，不替检查器证明规则正确。

## 已有固定任务边界与集成归属

[版本化任务与固定目标验收](next-iteration.md)已有有限实现及工程验收，结果见 [validation.md](validation.md)。以下说明这部分已有责任，不代表完整自然语言建模链或比较实验已实现。

| 位置 | 已有责任 | 不授予的权力 |
|---|---|---|
| protocols | `TaskStatement`、`TaskBinding`、`TaskContract`、`TaskAssessment` 的唯一严格交换定义；公共引用/报告完整性校验 | 不读取文件、不解释来源正文、不保存模型 |
| assurance | `prepare_task` 在内存中核对任务/来源原始字节、位置及显式映射；`assess_task` 执行固定计划并分别报告意图就绪与目标检查状态 | 不导入领域适配器、不产生模型提交、不认证真实用户意图 |
| adapters | `graph_reachability`、`trace_acceptance` 解释两个有限任务语义，通过 Checker 注入 | 不决定任务授权、不选择评价规格 |
| apps | 显式读取任务/来源路径，固定初始模型及计划；预览候选，符合保存条件时调用 kernel | 不用留出评价结果驱动选择或重试，不把模型保存说成应用交付 |
| tests/studies | 固定评价规格、参考实现、方法装配及其证据记录 | 不被运行包或任务 CLI 反向导入 |

固定任务入口的 TaskContract 原始字节引用由调用方在候选产生前确定。有限澄清入口先固定父任务和解释/探针，预览探索候选并接收回答，再由应用从固定探针与回答派生显式后继任务；后继保留父声明/义务/绑定，并在最终提案和验收前固定。探索不使用参考评价反馈，所选候选不参与目标派生。PreparedTask 与澄清 Session 均为可信进程内值，不是跨进程授权令牌。澄清预算限制候选、观察和问题数量；研究条件与论文预算仍由后续编排设计。任务信封不含行业 profile、论文条件或评价文件位置。见[有限澄清](clarification.md)。

任务到声明/计划的绑定与候选到报告的绑定分别负责不同完整性。两者成立仍不证明声明和规则语义忠实。TaskAssessment 没有 commit 字段；apps 只在必需意图 ready 且全部开发义务 satisfied 时调用原有内核保存。独立评价可随后失败，必须保留保存事实与评价失败，不伪造回滚或成功。

## 身份、变更与接受

元素 ID 不因改名变化，同内核实例历史内已使用的 ID 不可删除后重用；没有持久化跨实例的身份墓碑。元模型版本与模型修订各自管理，限定快照/来源引用绑定内容哈希；局部 dependencies 与 parent 使用元素 ID。迁移须显式说明映射、损失和消费者，当前没有通用迁移实现。impact 仅比较同项目/模型/元模型域，不能充当迁移影响分析。

意图、事实和假设用 category 区分；confirmed 是确认状态，不能改变来源类别。requirements 和恢复模块形成候选，kernel 经 preview/check/decide/apply 接受模型变化。检查报告绑定候选、计划、范围、前提和真实工具版本；接收成功字符串不等于执行检查。

修复改善、模型保存、业务操作许可、应用交付是四种决定。当前切片只处理修复进展和设计模型保存；有残余的保存不能被说成业务可运行。包含边不自动传播语义失效；影响看变更前后依赖，缺依赖信息为 unknown，历史报告保持不变。

生成期控制说明在哪一阶段排除哪些非法候选、哪些义务仍需终验。应用业务 UI 与服务实现通过版本化 CommandBinding 连接，业务权限在后端判断；代码前审阅绑定需求/候选版本，由 requirements 或对应提案消费者处理回答和编辑，不要求已有应用服务。文件物化必须区分 generated/human/third_party、目标路径和期望旧哈希，模型保存与文件写入不是一个已实现的全局事务。

## 方向方法与可替换位置

| 方向 | 研究问题与计划替换位置 | 独立验收与边界 |
|---|---|---|
| P1 自然语言建模与澄清 | requirements 从原文形成概念/关系/约束候选，保留来源与未决项，通过澄清细化领域元模型候选；固定元模型内的模型变更才使用现有 ChangeProposal | 候选表达的充分性、意图忠实、任务可支持程度与澄清成本；目前可运行显式有限解释澄清、原文请求/typed 候选检查及有限实例检查，新增有界真实语言调用入口，尚无独立语义通过；未决意图不强制二分类 |
| P2 合同保障 | assurance 的形式化/检查方法、generation 的控制阶段；由调用方注入具体检查实现 | 独立真值检查规格、绑定、候选符合性及相关错误；工具不同不自动意味着独立 |
| P3 任务交互 | interaction 的任务投影、解释与呈现；应用业务 UI 保持 CommandBinding 语义，代码前审阅保持需求/候选的版本和确认语义 | 真人的理解、操作和修改正确性；业务界面和开发审查台分别研究 |
| P4 代码恢复与演化 | code-intelligence 的恢复、追踪和语义差异；同步仍输出受控提案 | 带来源事实、覆盖缺口、影响漏检/过度失效；JSON diff 不等于一般语义恢复 |
| E 生命周期比较 | studies 装配代码中心、规格中心、模型辅助、元模型中心条件及消融 | 固定任务、版本、预算与独立验收，保留全体失败、成本和残余 |

以上大部分替换位置是目标接口，不宣称已有算法或实验运行器。当前真实扩展入口以公开 Python API 和已实现检查器边界为准；具体新增方法先有消费者和正反验收，再完善合同。

不预设应用试点。[两类异质配置](foundation-boundaries.md)通过显式 Checker 分别解释结构图端点/无环与有限自动机确定性/有限输入串接受；它们共用协议和模型提交合同。字符串编码并不使内核原生支持关系或行为语义；状态机模拟不是应用运行时。全图成员读取无法用现有指纹证明完备，两配置根必须保留 dependencies_complete=False，旧证据为 unknown 或 stale。既有订单夹具仍只承担有限回归。

研究运行要求见[公开协议摘要](../studies/lifecycle/protocol.md)，工程验收见[validation.md](validation.md)。

generation 的[有界构造](bounded-construction.md)通过领域回调消费固定编辑空间，DAG 适配器在提案前排除成环端点，所有任务义务继续终验；行为构造尚未实现。requirements 的有限消费者和 interaction 的有限审阅呈现已实现，implementation、code-intelligence、component-reuse 仍为 planned；工程实现不升级论文结论。固定编辑/候选空间不等于元模型表达空间的穷尽搜索，无可区分探针或有限无解不证明 representation_gap。
