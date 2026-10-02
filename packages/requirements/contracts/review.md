# model-review/0.1：有限审阅与回答

## model-review-local/0.2：实例与显式采纳

精确DTO及函数载荷见[消费者指南](../../../docs/model-review.md)。ReviewSession保留原封闭字段和初始原件，actions扩为ReviewAction|ProjectSubmission|ProposalAdoption的封闭联合；旧0.1存储无需迁移，序列化内容不自动改写。所有动作共用64项上限/ID空间，每条重放核对精确前缀head及当前request/candidate；后继review_ref对整个原件与动作链计算hash，版本计动作总数。

ProjectSubmission绑定当前合法候选、独立definition和head，purpose为example/counterexample/project，不修改检查结果含义。requirements纯转换登记ProjectModel与来源，apps保存前调用现有check_project验证结构；violated/unknown实例可保存，非法结构/错定义拒绝。保存成功改变review head。read_project可读取归档实例，check_saved_project只允许当前候选实例，输出当前request/candidate/definition/review/project引用和原DomainReport、required_residuals、population_complete。报告只读即时产生、不持久化为可复用认证；旧candidate或旧head不能用于新检查，语义忠实始终not_checked。

ProposalAdoption只引用当前已保存的完整提案，重新typed检查合法才采纳。当前request/source保持原件，candidate revision递增且hash绑定精确提案字节；原候选、回答、问题、残余、提案、确认、实例、父review_ref及采纳actor/text完整进入history。新候选的确认、当前实例及报告不继承，当前issues/residuals来自显式提案；允许用户改变要求，但保留旧未决，不将编辑内容伪装为原文。采纳不是自动修订、意图通过或kernel接受。

同ID同载荷返回already_recorded及首次recorded_review_ref/next_candidate_ref，当前review_ref可能已前进；新ID旧head或同ID异内容conflict。相同的ProjectSubmission在采纳后重发仅查询已记录结果，不把旧实例变为当前实例。存储继续同一model-review.json的锁、pending、fsync、replace、读验机制；任何失败不返回recorded，pending阻止旧缓存回读。历史保留受原24MiB/64动作资源边界限制，不截断历史。

这是可调用的有限子合同；总体设计归[消费者0.2](../../protocols/contracts/consumers-0.2.md)。protocols.review唯一声明ReviewAction与校验；requirements.review拥有ReviewSession、问题、回答/确认及提案含义；apps/model_review.py拥有本地存储。既有typed_domain/domain_language与包导出不变，直接导入新子模块。旧0.1仅四类动作；0.2新增实例与采纳见下节，仍无自动修订或认证；不宣称F1/F2完成。

## 输入与独立身份

`create_session(request:ModelingRequest, raw:bytes, session_id:str)`返回不可变ReviewSession。封闭记录为`{schema_version:"model-review/0.1",id,request:ModelingRequest,candidate_base64,actions:[ReviewAction]}`。request先经原validate_request验证，来源hash对应原文UTF-8字节；candidate_base64保存原始响应，最大256KiB，允许非JSON/非法UTF-8/非法AST进入审阅。超限拒绝创建，不能伪称已保存。session_id只作身份，不是磁盘路径。

引用均为ArtifactRef。request_ref哈希为规范request；candidate_ref的artifact_id为session_id加`/candidate`，revision=1、hash为原始响应SHA256；definition_ref单独使用定义id/version/规范hash，检查失败时null。候选issues/traces变化或字节排版改变也改变candidate_ref，即使definition相同。review_ref的artifact_id为session_id加`/review`，revision为动作数（初始0），hash为规范完整ReviewSession；回答后candidate不变也更新review_ref。编码/哈希统一用protocols.dumps/digest，原始响应hash例外按字节计算。

每个有question的有效issue生成一问题，引用hash绑定candidate_ref、source_ref、issue.id及question原文；重复文本不同ID仍是两个问题。无question的issue仍显示。初始非法候选提供独立诊断问题，raw原件/诊断可见，不从非法AST推测有效字段。问题状态open/answer_recorded/declined独立于resolution=unresolved；“不知道”是原文本回答，不转业务Null、false或已解决。

## 动作封闭载荷

```text
ReviewAction={schema_version:"model-review/0.1",id,project_id,
 request_ref:ArtifactRef,candidate_ref:ArtifactRef,expected_review_ref:ArtifactRef,
 question_ref:ArtifactRef|null,actor,kind:answer|decline|confirm|propose_edit,
 text,targets:[string],proposal_base64:string|null}
```

所有键必填。项目、请求、候选、预期审阅版本/hash须精确匹配；问题引用须属于同候选/来源。actor由可信本地宿主提供并记录，只表归属，不冒充认证身份。

|kind|限定输入|记录效果|
|---|---|---|
|answer|question_ref必填；text非空白；targets=[]，proposal_base64=null|追加原回答，问题answer_recorded，resolution仍unresolved，revision_status=pending|
|decline|同answer，text允许空串或保留拒答原文|追加拒答，问题declined，保留issue/残余，revision_status=pending|
|confirm|question_ref=null，targets非空且无重复，proposal_base64=null；text可为空|只登记targets与actor，不改变检查、忠实性、问题/残余或candidate|
|propose_edit|question_ref=null，targets=[]，text为非空修改理由；proposal_base64为完整候选原字节的规范base64|保留提案/旧绑定/actor并重用typed检查，合法/非法均作为adoption=pending提案，不覆盖旧有效候选|

confirm的元素目标为finite稳定ID；整体目标使用共享常量`WHOLE_CANDIDATE="review:candidate"`。finite禁止ID含冒号，因此不会碰撞。`$candidate`是合法元素ID，仅确认该元素；`review:flag`等未知标识拒绝。非法候选仅可整体确认“已看过该原件”，仍不获得语义通过。

提案可删除规则、residual或改变AND/OR；这些是显式用户需求修改，不强制继承旧业务意图，也不伪造为原文事实。原提案、旧候选和未决完整保留；引文只作attribution_only。有限语言不支持default等字段时提案检查rejected，原件仍可审阅。旧ReviewAction不会采纳/替换候选；adoption=pending等待显式ProposalAdoption接口，不是判定原residual永久不可编辑。确认/回答不能绕过此边界。

## 公开纯函数与视图

`review_input(session)`逐条重放校验整个链，返回脱离原会话的JSON值视图：review/request/source/candidate/definition refs、source_text、candidate_base64、candidate_text、inspection、terms（实体及字段）、relations、rules、residuals、issues、traces、questions、actions、proposals、confirmations。candidate_text与proposal.text仅是UTF-8 replacement显示；精确字节必须读base64。检查失败时结构数组为空，diagnostics和原件仍显示，不显示部分内容为已通过。检查结果始终requirement_fidelity=not_checked、instance_conformance=not_run。

`apply_action(session, action)`返回`(successor, receipt)`；receipt含status、action_ref、review_ref、recorded_review_ref、next_candidate_ref=null及revision_status。新动作status=recorded；同ID同规范载荷重试status=already_recorded，不追加版本，recorded_review_ref保留首次记录版本、review_ref是当前版本。相同ID但actor/text/绑定/原提案任一变化→conflict。已记录的相同动作允许越过过期expected_ref作幂等查询；新ID旧expected_ref冲突。action_ref按完整规范动作哈希，动作来源与SourceSpan分开，包含actor/text/旧candidate及source上下文，并明确asserts_original_source=false。

与完整草案对应：本profile直接以review_ref承担前置审阅版本绑定，不接受布局view_ref；actor字符串尚不是认证actor_ref；kind/text/proposal_base64分别收窄草案action/answer_text或reason/proposed_values。旧ReviewAction没有project_examples、外部reports、ApplicationSpec或代码交付入口；其next_candidate_ref为null，next_question_refs也不伪造生成。完整草案字段不能直接混入本封闭解码器。

## 本地保存、恢复和失败

apps公开函数为`create_review(project_dir,request,candidate_raw,session_id=...)`、`read_review(project_dir,expected_review_ref=None)`、`submit_action(project_dir,action)`。显式绝对路径的项目目录须已存在，一个目录一个会话，只创建固定model-review.json，不使用session/actor/元素ID拼路径；拒绝symlink/junction与非普通文件。输入目录权限由可信宿主管理，不防持有目录写权的恶意进程。

标准库独占创建`.model-review.lock`，覆盖读/创建/整个读改写周期，适用于同一本地文件系统上遵守该协议的调用者。锁已存在→busy，不自动抢锁。新内容独占写`.model-review.pending`、flush/fsync、同目录os.replace、重新读验后才返回recorded。写失败抛出原OSError或明确合同错误，残余pending阻止读写并返回incomplete_write，不读旧缓存作成功；锁释放失败也不返回recorded。进程崩溃留下锁/pending由宿主保留证据后人工核验恢复，本版本没有自动恢复/回滚器。只承诺本地进程级互斥及替换边界，不承诺网络文件系统或断电后目录元数据持久性。

存储为封闭`{head:ArtifactRef,session:ReviewSession}`。恢复核对head与规范内容hash/版本，校验request/候选原件、每个动作预期前缀及重复ID；截断、损坏、缺原件、错链均corrupt，不返回旧状态。无外部信任锚时不能识别恶意整体回滚到一份历史完整文件；调用方已有head时应传expected_review_ref，旧版本conflict。没有本地加密、认证或不可抵赖签名。

限额：候选/提案256KiB、动作512KiB、text 64K码点、targets256、每会话64动作、存储24MiB；用于约束完整重放的资源成本，不自动截断/压缩历史。超过限额unsupported。ContractError.code包括invalid、unsupported、conflict、corrupt、busy、incomplete_write；文件权限/写盘异常保留OSError。CLI打印error且退出2，成功输出视图/回执退出0；语言检查rejected的原件可成功保存供审阅，两种层次必须分开。
