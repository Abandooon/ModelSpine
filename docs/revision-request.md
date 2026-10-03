# 回答修订请求与有界执行

新增 `execution-revision-envelope/0.1` / `revision-context/0.2` 接口见[执行修订合同](../packages/requirements/contracts/execution-revision.md)。它支持外加复合问题、更正、真实回答分别归属，候选可引用原文完整行或已验证 question/action 原话。旧 source-only 合同及下列旧离线入口继续保留。

当前提示方法为 `typed-domain-revision-proposal/0.1.2`：明确 Constraint.context、关系端点、Get/Navigate、trace/issue 等交叉引用的声明 ID 与 ArtifactRef 来源，禁止使用显示名代替 ID；通用说明用户回答须结合所采纳的问题及更正，required 是 slot 存在要求，unknown 值不等于 optional。0.1.2 消除叶节点说明矛盾：仅 literal/instant/duration 有非 null value，分别为普通标量、UTC 时间戳、signed64 秒；其余算子 value=null。时间位移须为 Duration，负整数 literal 仍为 Int，不隐式转换。数组项须为指定对象而非解释字符串；ArtifactRef 精确字段为 project_id/artifact_id/revision/content_hash。候选/语言 DTO、严格解析和执行语义未改。此前真实响应虽 HTTP200/completed，仍因规则 context 使用显示名被拒绝；未证明是输出上限截断，原件不修补。后续 0.1.1 真实响应同样 completed，因 traces 数组混入字符串被拒绝；对未改写 definition 子树的诊断还发现时间加法使用 Int literal。两次均未证明是输出上限截断，原件不修补。新提示不保证输出合法、引用或语义正确，原失败与新调用计划分别保留。既存项目仍按已保存 method_instructions 重放；新 prepare 使用新提示/hash，旧冻结 run 不按新方法重放。

宿主先用 `model_review.record_clarification(project_dir, ExternalClarification)` 记录外加澄清，或用既有 submit_action 记录候选问题的 answer/decline。actor 是宿主归属，不是认证；不能把外加问题冒作某一旧 issue 的回答。完整 DTO 见合同和 `modelspine_protocols.review`。

有界调用使用 `language_modeling.prepare_revision_run(run_dir, project_dir, config, expected_review_ref=..., action_refs=..., task_id=...)`；它冻结一个输入、完整原文/父候选/原话/当前方法/payload，不联网。方法 `typed-language-run/0.4` 重用同一 Responses transport、原预算 reservation/receipt/锁、无自动重试。执行持有父审阅锁，核对父 head、所有原件及完整方法，期间其他协作写者收到 busy。输出文件使用排他创建，4MiB 单个准备工件上限、2MiB 响应信封和 256KiB 候选上限不扩大。

```text
python -B -I apps/language_modeling.py prepare-revision --run-dir ABS_NEW_RUN --project-dir ABS_PROJECT --bindings ABS_BINDINGS --task-id HOST_ALLOCATION_ID --env-file HOST_PRIVATE_CONFIG
python -B -I apps/language_modeling.py execute-next --run-dir ABS_NEW_RUN --expected-plan-sha256 PLAN_SHA --env-file HOST_PRIVATE_CONFIG
python -B -I apps/domain_modeling.py revision-inspect --envelope ABS_NEW_RUN/input-1/revision.json --response ABS_NEW_RUN/attempts/001/candidate.raw
```

bindings 恰有 expected_review_ref/action_refs。真实配置只由获授权宿主读取；本批开发和回归只用假配置。一个 run 只能执行一个修订 slot，task_id 须链接宿主累积预算分配；新目录不代表重置旧总预算。

执行成功也只保存 raw/inspection/receipt，不修改父候选或父审阅 head。宿主调用 `revision_proposal_from_run(run_dir, expected_plan_sha256=..., action_id=..., actor=...)` 校验工件，取得含固定 method_instructions 的 RevisionProposal，再由明确用户动作调用 `model_review.submit_revision_proposal` 登记、`adopt_proposal` 采纳。两步均重新核对旧页/父身份。登记推进审阅版本但候选不变，采纳才推进候选与历史。失败 API/不完整/错误模型/未知用量/非法候选都停止；raw 不补、不替换，不能生成可采纳提案。存储失败保留 pending，读取拒绝旧缓存成功。

`read_review` 投影版本为 model-review-local/0.3：actions 中 external clarification 保留整个 action、question_ref 和来源；proposals 含 revision_context；采纳后当前 view.revision_context 固定所用上下文，history 保留父视图与采纳动作。没有继承旧确认、旧实例或旧检查。以后仅修改当前提示不应影响既存项目恢复；旧动作中的方法原文及 hash 仍接受重放。

有限执行定义、集合未知精度及仅资格查询范围见 [finite-domain/0.2](../packages/protocols/contracts/finite-domain-0.2.md)。LocalWeb/ApplicationSpec v0.1 明确不支持新版定义，不能将本次资格检查称作业务提交或自动应用交付。工程假传输/人工夹具不证明真实修订成功。

## 保留的 revision-context/0.1 离线入口

此入口确定性整理原文、旧候选与用户回答/拒答，供未来明确接入语言装配；不调用模型、不生成或修补候选。它没有修改被冻结typed输入合同，也没有把回答塞回原文构造假来源。derived_modeling_request=null、generation_status=not_run、next_candidate_ref=null。

纯函数位于[requirements/revision_request.py](../packages/requirements/src/modelspine_requirements/revision_request.py)：`prepare_revision_request(session, expected_review_ref=..., action_refs=...)`。输入必须为可重放ReviewSession和精确当前head；action_refs为1–64个不重复、实际已记录answer/decline的action引用，可以包含历史候选的回答，每条保留其原parent_candidate/question/action/source绑定。未知回答不填默认，拒答原文本即使为空也独立保留，非回答动作或伪造引用拒绝。

封闭输出字段为ref、schema_version、review_session、action_refs、context、prompt。review_session保存可重放来源证据；context含parent_request_ref、parent_candidate_ref、parent_review_ref、original_source_ref/text、parent_candidate_base64、responses及未执行声明。每个response含原action、action_ref、question、该动作parent_candidate_ref/source_ref、provenance。它们是用户后续归属，不伪装SourceSpan，也不修改旧ModelingRequest。prompt保留原typed前缀并附明确的数据块/来源分离说明；不能直接冒称现有语言app已支持该信封。

`verify_revision_request(envelope)`以保存会话完整重放重新构造整个输出，核对head/问题/动作/原件/摘要和精确prompt。输出ref.content_hash覆盖除ref外的全部内容，同输入生成同字节；任一prompt/响应/来源篡改都会失败。非法原候选也可准备修订上下文，但仍保持非法原件和诊断，不变成合法替代。

重建使用当前typed提示；例如升级到`typed-domain-proposal/0.1.1`后，旧版本导出信封的prompt及摘要不再匹配，read/show会报`conflict: revision context/content hash mismatch`。旧导出按原方法版本保留与验证；新版从同一可重放审阅会话重新导出到新文件，不覆盖或修补旧信封。ReviewSession本身的解析合同未变。

[apps/revision_request.py](../apps/revision_request.py)提供`export_revision_request(project_dir, output_path, expected_review_ref=..., action_refs=...)`与`read_revision_request(path)`。目录和输出路径须显式绝对，源会话在原锁内读取；输出使用排他创建、fsync及重读验证，不覆盖已有文件，失败抛错且保留现场，不自动删文件或重试。24MiB上限，symlink/junction拒绝。actor仍为宿主归属而非认证。

```text
python -B -I apps/revision_request.py export --project-dir ABS_PROJECT --output ABS_NEW_FILE --bindings BINDINGS_JSON
python -B -I apps/revision_request.py show --output ABS_NEW_FILE
```

bindings封闭字段为expected_review_ref及action_refs，均为ArtifactRef JSON。错误退出2、不输出成功；本地工程演示明确hand_authored_engineering_only，API调用0。真实回答驱动自动候选仍not_run，不据此宣布F1/F2完成。
