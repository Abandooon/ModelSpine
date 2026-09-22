# 共享合同 v0.1

范围说明：本页保留既有 v0.1 合同及工程样例；具体业务对象、角色、单位不构成通用默认或指定应用。完整目标见[设计合同](../design.md)，其新增内容为 draft，不能据此推定已有源码支持。

S1 完成三场景自查；运行字段唯一权威定义位于 `src/modelspine_protocols/__init__.py`。本版本尚非 stable。protocols 拥有共享值对象、严格 JSON 编解码和 SHA-256 规范，不持有项目状态，不判定业务真值。消费者为其余八模块及平台 CLI。

## 身份和编码

`MetamodelRef(id, version)` 与 `Snapshot(project_id, model_id, revision, metamodel, metamodel_hash, elements)` 分开；元模型内容哈希也须相符。元素身份是 project/model/element 三元组，名字可变。`ElementRef(snapshot, element_id)` 必须匹配整个 SnapshotRef，不隐式解析至最新版本。

Element 的 kind/name/parent/properties/dependencies/dependencies_complete/category/confirmed/sources 均是模型内容。category 为 intent/fact/hypothesis，confirmed 不改变类别或来源。parent 只表达包含；dependencies 指向语义前提。领域字段由版本化 Metamodel 的 KindSpec/FieldSpec 定义；首期支持整数、字符串、布尔和元素依赖，不是任意 DSL。ArtifactRef 记录来源身份/版本/哈希，EvidenceRef 加定位和出处，路径不是身份。

KindSpec 中的 FieldSpec 名称必须非空，即使模型尚无该类型的实例也要检查。`validate_evidence_refs` 复用来源引用内容校验：模型校验中的 Element.sources 与提案预览中的 ChangeProposal.intent_refs 均要求非空来源项目/制品/版本、定位、出处及 64 位小写十六进制 SHA-256。引用集合可以为空，但 fact 元素仍须至少一个来源；这只验证引用完整性，不证明内容真实或意图忠实。JSON 解码完成不等于这些语义校验已经完成。

JSON 用 UTF-8、排序对象键、紧凑分隔符；元组编码数组，数组顺序保留。拒绝未知/缺失字段、重复 JSON 键、浮点/NaN、bool 冒充 int、未知操作及不支持 api_version。所有字段必填，只有声明可空者可 null。破坏性字段/语义变更升版并同步消费者；新增字段也需协同升级，不承诺严格解析器前向兼容，无隐式迁移。

## 变更、判定和证据

包版本 0.1.1-experimental 新增 `Checker(Protocol)`：`__call__(snapshot: Snapshot, plan: CheckPlan, scope: tuple[str, ...] | None = None) -> ValidationReport`。它是同步、确定性、无模型写入的进程内接口；执行器异常向调用方传播，JSON api_version 仍为 0.1，不引入新 JSON 字段。

kernel 校验返回报告的候选/计划哈希、规范范围、前提、非空工具身份/版本，以及范围内义务 ID/版本的完整唯一覆盖；错绑定或覆盖为 conflict，结构不合法为 invalid。执行器仍是可信依赖，绑定校验不证明规则真值或独立性。检查器读取的数据必须由模型显式依赖覆盖；`dependencies_complete` 是可信声明，当前不自动追踪读集。无法保证完整性时应标为不完整并保留 unknown，不能把跨范围未声明读取产生的证据视作可安全复用。

ChangeProposal 含 api_version/proposal_id/base/operations/intent_refs，六种操作是 Rename、SetProperty、SetDependencies、AddElement、RemoveElement、Confirm。整批在副本执行并验证最终结构；无任意 callback/metadata patch。新增 ID 唯一，删除不留悬空引用，重命名保留 ID。成功设计提交 revision+1（含无变化提案），与业务无变化写入规则分开。

元素 ID 在 kernel 本实例加载及此后已接受的历史快照内不得删除后重用，同一提案批次也不得 RemoveElement 后以相同 ID AddElement。需要新身份时使用新 ID；当前操作不能改写已有身份的 kind/category，也不能以删除重建模拟迁移。本规则不声明跨进程或重新加载后已恢复全部历史身份。

Preview 绑定提案哈希、候选哈希、候选快照与 ImpactSet。ValidationReport 只有此处一份共享结构；binding 包括候选哈希、计划哈希、范围、前提、检查器/版本，计划含规则和逐义务版本。outcome 为 satisfied/violated/unknown/not_applicable/error；非 satisfied 项保留为 residual。未支持项为 unknown，不是通过。

Decision 是内核登记许可，绑定基准、提案、候选、报告、策略、actor 和范围；不能用 approved=True 替代。checker 由平台注入可信进程，签发时重算报告以防外来 JSON 冒充检查。这不是跨进程认证系统。四类接受：修复进展、模型保存、业务订单批准、应用交付。默认 satisfied-save 要求非空范围内全部满足；显式 checked-save 可保存带残余的设计，不授予交付权限。

EvidenceRecord 保留原报告、基准及完整依赖指纹；Applicability 另算 current/stale/unknown。依赖完整且指纹、元模型、规则/工具/前提相符才 current；current 的 violated 仍是 violated。RunReceipt 只记录实际工具、输入/输出哈希、耗时和终态，不补造调用或成本。

## S1 全局推演

| 场景 | 合同链与状态归属 | 正例 | 反例及停止点 |
|---|---|---|---|
| A 新建应用 | requirements 给有出处意图→内核模型→assurance 义务→generation 候选→implementation 物化→interaction 命令视图 | 金额分、经理角色和批准失效策略可表达 | 未确认仍 hypothesis；unknown 不可交付；CLI 不是生成应用 |
| B 修改规则 | 需求提案→preview→check→decide→apply→迁移/重建→交互解释 | 阈值改变影响审批依赖，完整天气证据保留 | 旧基准 conflict；构建失败保留模型与失败记录，不冒称跨系统事务 |
| C 导入代码/组件 | code-intelligence 给事实/假设→component-reuse 给缺口→requirements 对齐意图→内核审查→implementation 所有权检查 | 代码中的阈值是 fact，是否期望另行确认 | 缺源位置不算事实；第三方/人工覆盖 conflict；相似不等于兼容 |

三场景覆盖九模块；远期为 reviewed 合同，运行子集才 exercised。统一 ContractError(code,message)：invalid/unsupported/conflict/forbidden/not_found；失败不部分写入。未来取消/超时保留 cancelled/unknown/error，当前不伪造这些运行事件。
