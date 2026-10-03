# 有界回答修订 execution-revision-envelope/0.1

本合同补充旧 [revision-request 指南](../../../docs/revision-request.md)，不改写原文 ModelingRequest、SourceSpan 或旧 typed-domain-candidate/0.1。新版定义用 [finite-domain/0.2](../../protocols/contracts/finite-domain-0.2.md)；候选常量为 `typed-domain-revision/0.1`。结构和完整引用通过仍不证明意图忠实，候选只能 unconfirmed。

外加澄清 `ExternalClarification` 属于协议模块 review，封闭字段：`schema_version="model-review-clarification/0.1", id, project_id, request_ref, candidate_ref, expected_review_ref, question_text, question_actor, correction_text, correction_actor, response_kind="answer"|"decline", response_text, actor, interpretation_text, interpretation_actor`。question/更正/答复逐字保存，各自归属；interpretation 只属于解释者，不是用户原话。更正和解释可为空，有文本必须有对应 owner；answer 不得为空，decline 可为空。没有默认/自动解析用户意图。它生成独立 question_ref（覆盖父候选、原来源、问题、更正、动作 ID）及 action_ref（覆盖整操作），不冒用候选旧 issue 的问题。宿主负责输入真实归属，无密码学认证声明。

ReviewSession 的纯转换 `apply_action`、本地 `model_review.record_clarification` 使用同一 expected-head / project / request / candidate 检查、全链重放、同 ID 同内容幂等、异内容冲突和 pending/busy 保存责任。它只推进审阅版本，不替换当前候选。原问题答案和外加澄清都可以被选择；伪造 action/question、跨项目/会话、旧版本拒绝。

`prepare_execution_revision(session,expected_review_ref=...,action_refs=...)` 返回封闭 `{schema_version,review_session,action_refs,context,prompt}`，版本 `execution-revision-envelope/0.1`。1–64 个不重复真实回答/拒答引用从当前/历史视图核对。context 版本 `revision-context/0.2` 包括父 request/candidate/review、原文 source/text、父原件 base64、完整回答归属、`derived_modeling_request=null` 和方法提示 hash。ref 绑定除自身外的 context；prompt 冻结完整新输出语法、完整原始 request、该 context 及准确 splitlines 行表。原源字节从不拼接回答；`verify_execution_revision` 重新重放并逐字段比较完整信封/提示。

新版候选恰有 `schema_version,request_hash,revision_ref,status,definition,traces,issues`。revision_ref 必须为该已验证 context.ref，request_hash 仍绑定原 request。Trace={element,evidence}，每定义元素一条。Issue={id,kind,text,related_ids,question,evidence}，kind 同旧合同。非空 evidence 列表只接受两个封闭分支：

- `{kind:"source",source_ref,span:{start_line,end_line,quote}}`：核对原 source 身份和逐完整行 LF 连接结果。
- `{kind:"action",question_ref,action_ref,part:"question"|"correction"|"answer"|"decline",quote}`：两个引用须同时属于已重放且被选择的记录，quote 等于该完整原话段。不能引用 interpretation 冒充用户证据。decline 不成为默认值或新需求确定性。

`inspect_revision_candidate(request,raw,context)` 的 context 是已重放信任边界，由 prepare/verify 或审阅转换构造，不能直接信任模型提供的 context。CLI `revision-inspect` 先验证完整信封。非法内容保留原件与 rejected 诊断，无删围栏/补 JSON/宽松字段或原文引文改写。每候选仍限制 256KiB。

`RevisionProposal` 封闭字段：`schema_version="model-review-revision-proposal/0.1",id,project_id,request_ref,candidate_ref,expected_review_ref,actor,action_refs,revision_ref,response_ref,proposal_base64,method_instructions`。模型执行结果只有原样提案，response_ref 是宿主归属的真实回执引用，不是认证或语义通过。method_instructions 保存实际生成方法指令的完整 UTF-8 文本，context 的 method_instructions_version（第一行）和 SHA256 都绑定它。历史重放只使用已保存方法，不能因当前提示措辞改变而让已登记/已采纳项目损坏；仅新 prepare 使用当前指令。改变已存指令而未改变原 revision_ref 必须拒绝。新调用计划仍冻结当前全部代码和完整 payload，旧导出/运行应按其固定方法验证，不能混为当前可执行计划。

`submit_revision_proposal` 根据当前父视图及提案固定方法重建 context、复查绑定并记录提案；错误候选可记录审阅但不能采纳。API 失败的 receipt 不可经语言入口导出可采纳提案；人工直接提案的来源不能因此伪称自动生成。

既有 `ProposalAdoption` 显式选择已记录 proposal。它重新检查当前 head、proposal、上下文及原候选字节，生成同项目/同 request 的后继候选引用与 history，保留父视图回答/未决，重新建立当前问题，不继承旧确认、实例、检查报告。用户可以明确改变需求，旧 residual 不被永久锁为不可编辑；其删除或改变的正当性仍需来源/语义审阅。不是内核接受/语义批准。

旧 `propose_edit` 仍只支持旧 source-only 候选；新版编辑必须带 RevisionProposal 上下文。旧 revision-context/0.1 export 仍是旧离线动作入口；不要把新外加澄清压成其中的旧单段 answer。依赖保持 requirements→protocols，无 apps/research 导入。
