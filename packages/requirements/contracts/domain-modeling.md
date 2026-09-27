# 原文输入与领域候选合同 0.1

状态：首个原文合同消费者，供 `modelspine_requirements.domain_modeling` 和 [CLI](../../../apps/domain_modeling.py) 使用。该模块准备输入、渲染提示并检查外部候选；没有语言模型传输或自动抽取，不修改旧有限澄清合同。

## 输入与产物

`prepare_request(raw, source, request_id=..., scope=...)` 接收原始 UTF-8 字节、宿主固定的 ArtifactRef、请求 ID 与范围，返回 ModelingRequest。无须元模型、Snapshot、Interpretation、Probe 或正确编辑目录。引用的项目/来源/修订/原始字节哈希以及 scope 都进入请求摘要；不可将响应自报的来源当作宿主预期输入。

`ModelingRequest` 的字段是 schema_version=`domain-modeling-request/0.1`、id、source、text、scope。text 保留原文换行及全部字符，重新编码后的 SHA256 必须与 source 相符。`modeling_prompt(request)` 产生固定 `domain-proposal/0.1` 指令、请求摘要与完整输入；只使用该输入与通用产物合同，不读取参考答案、模型目录或历史缓存。

`inspect_candidate(request, response_bytes)` 接收宿主请求和完整候选 JSON，严格解析为 DomainCandidate：

| 字段/对象 | 语义 |
|---|---|
| 顶层 | schema_version=`domain-modeling-candidate/0.1`、id、version、request_hash、status=`unconfirmed`，以及下列五个数组 |
| concepts | id、name、description、evidence；定义概念类型，非已存在项目对象 |
| attributes | id、concept_id、name、value_type、evidence；type 为 string/integer/boolean 或 null（未确定/当前不支持），不自动默认 string |
| relations | id、name、source_concept、target_concept、targets_per_source、sources_per_target、evidence |
| rules | id、text、related_ids、formalization=`not_formalized`、evidence；保留条件、例外与原始规则含义，不宣称已有解释器 |
| issues | id、kind、text、related_ids、question、evidence；kind 为 ambiguity/conflict/missing_information/unsupported，question 可为 null |

关系两端必须引用 concept，属性必须归属 concept。规则 related_ids 指概念/属性/关系；issue 可指上述对象或规则。所有数组共享唯一 ID 空间；来源无法形成定义时，可仅返回有依据的 issue，不允许全空结果冒充完成。

基数由 minimum 和 maximum 表达，适用于每一个对应端点：targets_per_source 是“每一 source 有多少 target”，反向相反。minimum 为非负整数或 null；maximum 为非负整数、`unbounded` 或 null。null 只表示未知，不能同时表示零或无上限；已知上下界须有序。未知属性类型或基数须关联明确 issue。条件性的数量限制（例如当前未归还的借用数量）先保留为规则，不冒充全部历史关系的无条件总基数。

所有候选项须有 evidence，元素为 SourceSpan(start_line, end_line, quote)。行号是原文 `splitlines()` 的一基、闭区间，quote 必须逐字等于这些完整行以 LF 拼接。引用换行规范化仅用于 quote；原始来源哈希不规范化。来源身份由整个 request_hash 绑定，因此单原文合同不在每个 span 重复 ArtifactRef。多来源、引用片段内偏移和跨候选确认尚不属于本版。

## 检查、未知与失败

返回 CandidateInspection，包含 candidate、原响应字节 response_hash、structure=`valid`、semantics=`not_checked`、rule_execution=`not_implemented` 与 unresolved_ids。后者只枚举已上报 issues；为空不证明需求完整。即便引文匹配，也不能证明引文支持候选含义。规则、基数定义和结构有效不等于运行时已经执行这些语义。

请求和候选的解码字符串须可编码为 UTF-8；JSON 转义的孤立代理字符同样拒绝。CLI 在创建输出文件前完成编码，写出不额外追加合同外的换行，恰好达到请求上限的文件可原样回读。

来源或请求错绑定为 conflict，非法 JSON/类型/字段/ID/引用/基数为 invalid，超过合同载荷范围为 unsupported；都抛 ContractError，不产生部分有效候选。复用 protocols 严格解码，拒绝重复键、未知字段、bool 冒充 int、浮点与非有限数。原始来源上限 64 KiB、序列化请求 512 KiB、响应 256 KiB、候选项总数 256；它们是解析边界，不是模型 token 或费用预算。

候选整体未确认；本入口不接受/确认领域定义，不向内核提交，不执行真实业务，也不对未知内容补答案。下一语言适配器须保留供应商、模型、方法版本、原响应、真实用量和失败；本版没有该适配器，也不以外部文件来源自述替代真实调用证据。

## 当前消费者与验收

CLI 的 prepare / prompt / inspect 分别消费输入合同、提示和候选检查结果。inspect 的退出 0 仅表示结构与引用校验完成；结果明确 generation_provenance=`not_verified`、model_committed=false，不能当作自然语言生成或语义通过。输入或文件错误退出 2，既有输出文件拒绝覆盖。

包内单元与应用集成测试使用显式手工候选检验边界。独立[原文开发样例](../../../tests/fixtures/domain-modeling/README.md)预先固定语义期待，覆盖清晰、歧义/冲突、不支持规则及仅改变条件/上限的原文对照；这些期待不进入提示。合同测试与独立语义验收分开，尚未运行抽取器或正式研究。
