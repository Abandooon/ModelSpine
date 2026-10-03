# 有限候选审阅呈现合同

本实现消费 [A 的 model-review-local/0.2](../../requirements/contracts/review.md)，只拥有呈现和浏览器内草稿。旧 ReviewAction/model-review/0.1 存储仍由 A 原样读取。状态、重放、检查、保存与回执均归 A；不引入另一份审阅状态机。完整交互设计仍见 [design.md](design.md)。2026-10-02 离线包覆盖实例、显式采纳、修订材料及有限应用配置，无外部模型/API/余额/目录请求。

2026-10-03扩展消费A的model-review-local/0.3及最终method_instructions增量。旧会话仍由同一read_review读取，新类型不伪装成旧ReviewAction的kind/text；新增行为不表示整体设计或F2完成。

`modelspine_interaction.review_ui` 提供：

- `project_review(view) -> list[dict]`：将 A 已核验视图投影成纯文本、表头、表格行和完整详情文本；不修改输入、不做合法性或表达式求值判断。
- `format_expression(expr, schema_version="finite-domain/0.1") -> str`：只格式化对应版本，二元表达式全加括号。v1保留field/count方向；v2明确self/var/get/navigate/filter/count的对象、方向及变量绑定，instant/duration/add/sub不求值或换算。UTC整秒不转时区，Python保留Int64，未知版本/算子明确ValueError，不自动回退旧语法。
- `definition_version(view) -> str | None`：读取A已核验的inspection.checks.candidate.definition.schema_version；非法原件返回None，不从算子猜版本。
- `project_instance(model) -> list[dict]`：ProjectModel 对象/字段/值状态与关系表，保留 population_complete 及精确值；不填补缺失/unknown/null。
- `project_report(report) -> dict`：逐项展示既有 DomainReport 的 obligation/target/status/reason，保留 satisfied/violated/unknown/error/not_applicable；不合成整体语义通过。
- `spec_template(view) -> str | None`：只为finite-domain/0.1提供绑定本页来源与候选的未配置结构；不填权限、任务、初始数据或验收样例。v2/其他版本/无有效定义返回None；app的所有spec读写/准备/确认入口也显式拒绝不支持版本，页面不显示旧表单冒充支持。
- `review_page(token) -> str`、`review_asset(name) -> bytes`：固定页面及封闭的 JS/CSS 资源。token 属性转义；候选、原文、用户文本仅经 textContent/createTextNode 渲染，无 innerHTML。

主视图包含术语/字段及类型、必填/可空、关系名称及端点/双向基数、规则上下文与三个独立谓词、问题/残余和动作状态。完整 JSON、原响应文本/精确 base64、来源和身份引用保留在展开详情。非法候选不猜测合法结构，仍展示原件和诊断。无候选结构不是检查通过。

精确显示依据为服务器产生的 `presentation` 字符串与原件，而不是浏览器解析后 `view` 中的数值。JavaScript Number 会舍入超出安全整数范围的 Int64；前端不得据此重建表达式、完整详情或候选。服务器先用 Python 对原始核验视图格式化规则和 JSON 详情，再作为字符串传输；原响应字符串/base64独立保留精确字节。无需改变 A DTO 或引入另一套 JSON 框架。

应用 `apps/model_review_ui.py` 装配 A 的 `create_review/read_review/submit_action/save_project/check_saved_project/adopt_proposal` 和公共 `ReviewAction/ProjectSubmission/ProposalAdoption`。实例原件读取直接消费 read_review.projects/history，不另造存储或实例读取逻辑。本包仅导入标准库，当前 `runtime_dependencies=[]`；公开视图的设计依赖不伪报为 Python 导入。应用使用已注册的 `bootstrap.activate(("interaction",))`；D 未修改 bootstrap，统一登记由总领负责。

浏览器每次载入固定 `request_ref/candidate_ref/review_ref/question_ref`，四种动作直接构造公共载荷。`review:candidate` 为整体原件，`$candidate` 为合法同名元素。actor 在启动时固定，只是归属，不是认证。每次提交生成独立动作 ID；没有后台重试、自动换版本或合并。收到真实 recorded/already_recorded 回执才显示已记录；保存后页面仍绑定原版本，用户显式从新窗口读取最新记录继续。旧页冲突、读写失败和网络无回执均显示错误并保留输入；可能已落盘但丢失回执时要求重开核验。草稿只存页面内存，关闭页面不保留草稿；再次打开恢复的是 A 已保存记录。

answer/decline 保留 unresolved；confirm 不改变检查和候选；propose_edit 提交完整 UTF-8 候选文本（可非法），检查和 adoption=pending 由 A 返回，保存提案不覆盖原候选。取消只重置当前表单，布局仅切换 CSS，不产生动作。当前不支持自动修订、语言生成候选或应用生成；用户页面以行为语言说明限制。

## 离线材料与确切应用配置

应用装配 A 的 `export_revision_request/read_spec/save_spec`、公共 `LocalWebSpec/acceptance_digest/spec_content_hash/assess_application`，实际注入现有 `check_project`；interaction 不导入这些应用函数、不复制就绪判定或保存逻辑。

| HTTP | 封闭输入与行为 |
|---|---|
| POST /api/revision/export | expected_review_ref、action_refs；服务自建临时目录调用 A 公开导出函数，返回完整 envelope_text，随后清理临时目录。无客户端文件路径。 |
| GET /api/spec | A read_spec；仅其固定 application-spec.json 不存在表示 not_saved，其余错误保留；已存版本及历史引用、实际 assessment、精确 spec_text。 |
| POST /api/spec/save | spec、expected_spec_ref；A save_spec 校验 live review/head/version 并持久化，真实回执后才显示保存。 |
| POST /api/spec/prepare | 同上加 next_version（可 null）；核对页面审阅与配置 head。按显式版本更新 version，通过公共摘要函数计算 acceptance case 的 content_hash；用真实 checker 评估，并返回完整 spec_text/content_hash。只读，不补配置/预期，不产生确认。 |
| POST /api/spec/confirm | spec、expected_spec_ref、content_hash、id；核对准备后的内容 hash、页面审阅/配置 head 与全部来源绑定，组装既有 ReviewAction confirm / WHOLE_CANDIDATE / approve-local-web-spec:<hash>。真实回执后仅替换 spec.review_ref 和 confirmation_refs，返回精确 spec_text，尚未保存 spec。 |

这些小型 HTTP 参数类型只是公开函数参数包装，不是共享动作或存储合同。明确确认可留有其他就绪阻碍，但绝不能把它们转成通过；保存/重读都采用 A 的实际 assessment。准备计算样例摘要不替代实际检查，至少一个完整成功公开实例及其他要求仍由 A 决定。

用户看到完整准备内容并主动勾选；输入改变即取消准备。确认 hash 排除项由 A 定义，UI 不自行散列。确认后其他旧动作表单仍绑定载入时 review，专用配置流程只消费该次明确确认回执。确认与 spec 保存不跨文件合成事务：并发更改后保存可能冲突，确认仍留痕，UI 保留草稿且不自动重试。重新读取在新窗口进行。相同内容按 A 幂等合同可能 already_recorded；不同旧稿409。

完整配置及下载材料只通过服务器字符串传输。JS 不解析再序列化其中的数值；身份字符串可从已解析引用使用，Int64 只能取 spec_text/envelope_text/原件。上传仍受512 KiB统一限制，导出大小由 A 的24 MiB限制负责；不增加 lossless JSON 框架。版本/内容摘要与 DTO 细节折叠，主界面描述用户动作与阻碍。

## 离线实例与采纳

2026-10-03新增三个封闭HTTP入口：

| 入口 | 公共接口与边界 |
|---|---|
| POST /api/clarification | ExternalClarification → A.record_clarification。问题、更正、回答/拒答、解释及各自归属分开，原始source不覆盖；actor仍是启动归属标记。 |
| POST /api/revision/proposal | RevisionProposal → A.submit_revision_proposal。页面绑定父request/candidate/review；表单只接收action_refs/revision_ref/response_ref/proposal_base64/method_instructions五项。冻结方法原文必填，无当前提示默认值或旧字段猜测；登记不改变候选，待显式adopt_proposal。 |
| POST /api/project/eligibility | 封闭参数project_ref/expected_review_ref/operation/target → A.check_saved_eligibility。只检查已保存当前实例；不直调checker、不复制求值/存储。 |

规则表按明示版本区分invariant库存完整性和eligibility操作资格，后者独立显示operation。浏览器资格检查必须主动选择操作与目标；结果显式标action_execution:not_run，不表示提交、历史保留或权限执行。原check_saved_project用于结构/库存检查；未知/error/必要残余不合成通过，也不跨候选继承。新HTTP分支沿用Host/Origin/token/CSP、512KiB与错误草稿约定。

ExternalClarification按schema_version读取，不访问不存在的旧kind/text。question/correction/response/interpretation分别展示原话和归属，解释明确非用户逐字原话；questions.kind区分候选原问题、诊断问题和外加澄清。修订上下文在后继主页面显示父回答归属，在历史保留全部原件。typed-domain-revision/0.1证据按source.source_ref/span与action.question_ref/action_ref/part/quote投影，不能拼接成原文SourceSpan。完整绑定和原件保留详情，来源正确性由A检验。

RevisionProposal由A保存生成时method_instructions，重放不依赖当前INSTRUCTIONS；UI只传入给定冻结原文并展示方法版本/hash，不实现兼容重放或迁移。response_ref归属不等于已认证语言调用，仍显示generation_provenance:not_verified。缺字段、方法/上下文错绑定、旧页失败保留输入，不自动重试或补值。此UI不生成语言产物；新式澄清的执行修订下载尚未装配，原普通答复下载保留并明确边界。

本包runtime_dependencies仍为[]，新增public provide仅definition_version，既有format_expression增加可选版本参数。app新增导入A三个函数及ExternalClarification/RevisionProposal；没有新第三方依赖、共享状态或研究导入。

实例JSON文本嵌入 ProjectSubmission 的 project 字段，直接送服务器 `loads(ProjectSubmission, raw)`；前端不对实例数值做 JSON.parse→JSON.stringify。用户显式选择 purpose=example/counterexample/project，不将反例的 violated 反转为通过。模板按钮只填无对象、population_complete=false的可编辑结构，不生成或自动保存实例。A核对引用、结构与保存条件；实例列表同时显示purpose、归属、request/candidate/definition/based_on_review引用以及精确原件。存储为严格typed ProjectModel，不承诺保留用户JSON排版。

`POST /api/project`保存公共 ProjectSubmission；`POST /api/adopt`消费公共 ProposalAdoption；`POST /api/project/check`只接收封闭的 `{project_ref, expected_review_ref}` 函数参数。这是应用HTTP参数，不新增共享动作。检查调用A的check_saved_project，返回原报告及服务器精确字符串投影；只读，不改变head/保存报告，不自动在保存后宣告通过。界面分别展示本次即时报告和会话未缓存报告状态。新路由沿用全部来源/大小/方法/错误检查。

只有形式检查valid的已保存完整提案显示采纳表单；用户须复核原件、填写理由并明确勾选采纳。UI资格判断不替代A的重新检查与绑定校验。真实成功回执显示前后候选版本及next_candidate_ref，链接打开后继；非法提案的原件/诊断仍在详情，不可采纳。不存在自动采纳、自动清未决或kernel接受。

版本导航仅选择本次read_review返回的当前/历史快照，不读取URL指定的磁盘路径；fragment只选择已返回的候选修订号。历史只读，保存原候选、回答、问题、残余、提案、确认、实例和采纳来源；当前版本不继承旧确认/实例结果。切换版本仅隐藏当前表单，返回后草稿仍在。所有提交及即时检查仍绑定页面所见head；旧页冲突409，不自动换版重发。旧实例使用新head请求检查也由A拒绝，不能把历史结果当新结果。

服务只监听 `127.0.0.1`，一个进程绑定一个显式已存在绝对目录，不接受 URL/请求目录选择。精确 Host、Origin、Fetch-Metadata（存在时）和随机页面动作能力串约束请求；API 读取也须能力串；POST 必须同源、JSON、单一长度且不超过 512 KiB，拒绝重复边界头/Transfer-Encoding，连接读超时 10 秒。资源路由封闭，未知方法不调用存储，CSP 禁止内联脚本/嵌入，响应 no-store。不是认证系统、多租户隔离或防本地恶意进程方案。A 独占管理目录校验、锁和写入；失败不抢锁、不修复、不回旧缓存。

验证范围见 [启动和验收说明](../../../docs/model-review-ui.md)。工程样例和浏览器自动化只验证有限 UI，不证明意图忠实性、真实语言链或 F1/F2 完成。
