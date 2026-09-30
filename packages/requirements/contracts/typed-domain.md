# typed-domain-candidate/0.1

首个消费者为apps/domain_modeling.py的typed-prompt、typed-inspect与check-project。原文仍沿用ModelingRequest/SourceSpan 0.1，旧R1命令不换解释。完整结构与求值见[finite-domain/0.1](../../protocols/contracts/finite-domain-0.1.md)，完整设计[language/0.2](../../protocols/contracts/language-0.2.md)。

新增有限审阅消费者见[model-review/0.1](review.md)。它以ModelingRequest和外部响应原字节建立审阅，不更改本候选格式或既有inspect行为；检查拒绝的原件仍可显示与记录回答。candidate_ref绑定响应工件字节而非definition_ref；用户回答/编辑另有来源和审阅版本。完整候选提案重新调用inspect_typed_candidate，结构通过仅为valid，未采纳/自动修订仍pending/not_run，原文引文匹配不证明用户修改后的需求忠实。无服务器、UI或真实模型调用。

`typed_modeling_prompt(request)`只消费经过校验的原文请求和固定语言指令，含request_hash；无正确模型、业务目录或答案选项。`inspect_typed_candidate(request,raw)`检查严格交换格式、有限语言良构/类型、宿主请求绑定、每项来源覆盖及issues。TypedCandidate字段为schema_version、request_hash、status=unconfirmed、definition、traces、issues；全项trace不证明语义充分或忠实。所有定义元素必须恰有一条trace，其evidence为非空准确原文行引文；规则与Residual也不例外。问题仍可开放文本，不将未答变成否定。

检查返回TypedInspection：candidate、response_hash、language=valid、definition_consistency=references_and_types_checked、requirement_fidelity=not_checked、instance_conformance=not_run、execution_support=finite_core|residuals_present。有限语言不含全部语义族；需要的内容超出配置时保留Residual及来源，不删条件、不标结构合法等于可生成完整应用。来源缺失、错绑定、非法表达式无部分成功。256KiB响应上限继承R1，表达式另有深度/节点上限，超深JSON也明确拒绝。

真实语言适配器仍未配置：需要供应商/API、模型、认证环境变量名及可执行预算；本轮不选默认值、不读取密钥正文、不发付费调用，不将人工响应标成自然语言生成。后续真实调用固定方法版本、输入/原响应字节与hash、实际模型、请求时刻、调用/失败/用量及预算停止，不静默切模型或重试。开发检查反馈可供协议内修复；B留出答案与终验反馈不进入同轮生成/修复。

完整需求工程交换设计（不由此次有限解码器实现）：`RequirementSet={id,version,source_refs,statements,terms,scenarios,questions,answers,conflicts,acceptance_refs}`；`Statement={id,modality:must|should|may|undetermined,text,condition,exceptions,scope,priority,source_refs,confirmation}`；`Term={id,label,meaning,source_refs,ambiguities}`；`Scenario={id,actor,preconditions,steps,expected_outcomes,source_refs}`；`Question={id,version,statement_refs,trigger,text,status:open|answered|declined}`；`Answer={id,question_ref,expected_requirement_ref,actor_ref,text,status:answered|declined,source_ref}`；`Conflict={id,statement_refs,kind:contradiction|scope|terminology,explanation,resolution_ref?}`。引用均使用有版本/hash的公共引用，回答追加不可覆盖；statement模态未定不得降为may。例：must“仅当前计数”与must“全部历史计数”作用域相同产生冲突；答“仅当前”新版本解除所指冲突，拒答仍open/declined，不改规则为false。需求层不要求提前提供正确领域类型或答案选项。
