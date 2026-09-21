# 内核合同 v0.1

范围说明：本页保留既有 v0.1 合同及工程样例；具体业务对象、角色、单位不构成通用默认或指定应用。完整目标见[设计合同](../design.md)，其新增内容为 draft，不能据此推定已有源码支持。

拥有已接受设计快照、历史、决定登记、提交收据和检查证据；不拥有应用订单或文件。供应给模型消费者；只导入 protocols，checker 由应用注入。

检查器实现 `protocols.Checker`，同步返回确定性报告；kernel 的统一边界验证报告结构、候选/计划/范围/前提绑定、工具身份及义务 ID/版本完整唯一覆盖。错绑定/覆盖返回 conflict，错误结构返回 invalid，执行器异常传播且无部分提交。decide/apply/record_evidence/evidence_status 均通过此边界；提交中证据适用性使用本次已经验证的报告绑定，不额外重复执行检查。此加强行为属于包版本 0.1.1-experimental，JSON api_version 保持 0.1。

公开操作：snapshot(revision=None)、resolve(ElementRef)、preview(ChangeProposal)、decide(proposal,report,actor,policy)、apply(proposal,decision,actor)、record_evidence(report)、evidence_status()、add_note(text)。输出为隔离快照、严格引用、Preview、Decision、Commit、EvidenceRecord、Applicability 或文本注记；没有 metadata 全状态回调。

预览校验项目/模型/修订/元模型/哈希；提交锁覆盖重预览、许可核对、版本比较及快照/收据写入。同 proposal ID+内容+actor 的重试返回原收据，不同内容 conflict。失败不增版本、不改变历史或证据。只承诺单进程同一实例的并发线程内存事务，无持久化、跨进程 CAS 或崩溃恢复。权限在决定与提交两处验证。

影响使用 before/after 两图的 changed→dependent 闭包；包含关系不传播。证据从范围向 prerequisites 展开，完整性未知则 unknown；指纹或相关依赖变化 stale；完整无关范围 current。计划/工具整体改变保守 stale，不宣称精准逐规则迁移。原始报告不改写。

检查器实际读到的数据须由模型依赖覆盖；`dependencies_complete` 是上游可信声明，当前没有自动读集追踪。输出绑定验证不证明语义或依赖完整，检查器跨范围读取却不声明依赖时不能据此认定证据可复用。

A 正例：预览重命名保留 ID/revision；反例：预览即写入。B：删依赖仍走旧图，两旧基准只能一提交；反例：全根传播天气失效。C：恢复提案仍走提交，notes 不能注入模型。invalid/not_found/conflict/forbidden/unsupported 均无部分状态；共享版本不匹配拒绝，元模型迁移暂未实现。
