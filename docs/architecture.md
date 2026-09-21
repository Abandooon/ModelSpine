# 框架、模块与研究扩展

ModelSpine 是元模型中心的软件开发框架，ModelSpine Studio 是目标平台。平台能力、论文方法和实验结论分别管理；公共内核服务所有方向，不等同于需求方向的研究贡献。比较优势尚未得到本平台实验支持。

## 九模块的职责

| 模块 | 拥有的状态或产物 | 公开边界及当前范围 |
|---|---|---|
| [protocols](../packages/protocols/contracts/design.md) | 共享身份、版本、交换值对象、错误 | 已实现严格 v0.1 JSON 和有限标量元模型；不持有项目状态 |
| [model-kernel](../packages/model-kernel/contracts/design.md) | 已接受快照、决定、提交、证据适用性 | 已实现单实例内存事务、六种操作和依赖影响；无持久化或跨进程事务 |
| [requirements](../packages/requirements/contracts/design.md) | 需求证据、问题、答复、诊断、候选 | planned；产生模型提案或元模型扩展建议，无直接模型写权 |
| [assurance](../packages/assurance/contracts/design.md) | 义务、形式化、检查计划、逐项报告 | 已实现设计字段 integer_range/equals；一般形式化和外部求解器仍属设计 |
| [generation](../packages/generation/contracts/design.md) | 生成计划、候选、修复建议、运行轨迹 | 已实现单字段候选控制和纯报告比较；无 LLM 或完整修复循环 |
| [implementation](../packages/implementation/contracts/design.md) | CommandBinding、文件计划、构建、迁移计划 | planned；承担文件所有权、业务绑定和交付边界 |
| [interaction](../packages/interaction/contracts/design.md) | TaskView、交互计划、用户请求 | planned；业务界面与开发审查台分开，无模型或业务授权权力 |
| [code-intelligence](../packages/code-intelligence/contracts/design.md) | 实现事实、恢复假设、追踪、语义差异 | planned；必须记录来源和未覆盖部分，不能以代码事实覆盖意图 |
| [component-reuse](../packages/component-reuse/contracts/design.md) | 外部能力说明、兼容性结果、适配建议 | planned；相似或来源声明不等于行为兼容 |

`contracts/design.md` 描述目标，`contracts/v0.1` 描述当前合同或有限设计；成熟度与实现状态由各 module.json 标明。目标中的新字段不自动进入严格 v0.1，也不承诺任意语言、任意领域或完整应用生成。

## 依赖与装配

当前运行依赖是 `model-kernel → protocols`、`assurance → protocols`、`generation → protocols`；protocols 不依赖其他能力包。其余五模块没有运行实现。module.json 的 `runtime_dependencies` 表达这层实际依赖；planned 模块为 null，不能将 null 解读为已实现独立运行。

`depends_on` 保留目标设计所消费的能力合同：requirements/code-intelligence 消费 kernel，assurance 消费 kernel 的模型边界，generation/component-reuse 消费 assurance 的公开义务与报告，implementation 消费 generation，interaction 消费 kernel 与 implementation 的 CommandBinding。设计依赖不授权直接导入另一包内部实现。

模块 manifest 的文件引用相对所在模块目录；`reference_sources.asset_id` 和 `review_targets` 是来源、研究工作区联动的逻辑标识，不是 Python 包或运行依赖。公共来源、验证入口均在本仓库内。

apps 负责装配当前能力；studies 可装配替代方法、检查器、条件和记录器。运行包不能反向导入 apps/studies/tests/research。适配器实现公开合同，按调用显式选择；失败不自动换后端。尚无实际消费者的扩展保持设计，不预建插件注册中心、运行框架或空包实现。

当前真实检查器入口是 `protocols.Checker(snapshot, plan, scope=None) -> ValidationReport` 的同步调用合同。kernel 核对返回报告结构、候选/计划/范围/前提绑定及义务覆盖，执行器异常不被转成成功。替换检查器不需修改 kernel 的能力依赖。模型依赖必须覆盖检查器实际读取的数据；`dependencies_complete` 是可信声明，当前不自动追踪读集，报告绑定校验不能证明依赖完整或语义正确。

## 身份、变更与接受

元素 ID 不因改名变化；元模型版本与模型修订各自管理，所有引用绑定内容哈希。迁移须显式说明映射、损失和消费者，当前没有通用迁移实现。

意图、事实和假设用 category 区分；confirmed 是确认状态，不能改变来源类别。requirements 和恢复模块形成候选，kernel 经 preview/check/decide/apply 接受模型变化。检查报告绑定候选、计划、范围、前提和真实工具版本；接收成功字符串不等于执行检查。

修复改善、模型保存、业务操作许可、应用交付是四种决定。当前切片只处理修复进展和设计模型保存；有残余的保存不能被说成业务可运行。包含边不自动传播语义失效；影响看变更前后依赖，缺依赖信息为 unknown，历史报告保持不变。

生成期控制说明在哪一阶段排除哪些非法候选、哪些义务仍需终验。UI 与服务实现通过版本化 CommandBinding 连接；业务权限在后端判断。文件物化必须区分 generated/human/third_party、目标路径和期望旧哈希，模型保存与文件写入不是一个已实现的全局事务。

## 方向方法与可替换位置

| 方向 | 研究问题与计划替换位置 | 独立验收与边界 |
|---|---|---|
| P1 需求澄清 | requirements 的诊断、提问选择、细化策略；通过 ChangeProposal 消费公共模型合同 | 留出任务的充分性、意图忠实与澄清成本；未决意图不强制二分类 |
| P2 合同保障 | assurance 的形式化/检查方法、generation 的控制阶段；由调用方注入具体检查实现 | 独立真值检查规格、绑定、候选符合性及相关错误；工具不同不自动意味着独立 |
| P3 任务交互 | interaction 的任务投影、解释与呈现，保持 CommandBinding 语义相同 | 真人的理解、操作和修改正确性；业务界面和开发审查台分别研究 |
| P4 代码恢复与演化 | code-intelligence 的恢复、追踪和语义差异；同步仍输出受控提案 | 带来源事实、覆盖缺口、影响漏检/过度失效；JSON diff 不等于一般语义恢复 |
| E 生命周期比较 | studies 装配代码中心、规格中心、模型辅助、元模型中心条件及消融 | 固定任务、版本、预算与独立验收，保留全体失败、成本和残余 |

以上大部分替换位置是目标接口，不宣称已有算法或实验运行器。当前真实扩展入口以公开 Python API 和已实现检查器边界为准；具体新增方法先有消费者和正反验收，再完善合同。

不预设应用试点。通用支持范围用语义不同的模型配置检验：结构与字段、约束及状态效果、来源与追踪等能力分别说明。静态字段切片不能代表行为语义已支持；既有订单夹具只承担有限回归。

研究运行要求见[公开协议摘要](../studies/lifecycle/protocol.md)，工程验收见[validation.md](validation.md)。
