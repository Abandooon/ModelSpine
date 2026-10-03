# 有限本机Web应用子合同 local-project-web/0.1

目标是用户明确选择的Python标准库本机服务和静态页面：编辑ProjectModel、服务端check_project、显式保存、读取。它不是BESSER自动降级，也不是完整ApplicationSpec实现。总体合同仍由[consumers-0.2](../packages/protocols/contracts/consumers-0.2.md)统筹；本profile不制造finite语言没有的Operation/Policy，不覆盖域权限、远程集成或后台业务。生成器由独立消费者实现，本入口不生成应用。

当前目标只接受 `finite-domain/0.1`。可审阅、可检查的 `finite-domain/0.2` 仍返回 `unsupported_definition_profile`，规格保持 draft；携带新版检查器依赖不启用新版应用生成。

共享API在[protocols/application.py](../packages/protocols/src/modelspine_protocols/application.py)。实现包可以直接导入LocalWebSpec、各嵌套DTO、validate_spec、spec_content_hash、acceptance_digest、assess_application；该模块不导入apps，也不执行I/O。`assess_application(spec, verified_review_view, checker=...)`要求宿主提供已重放核验的审阅视图及现有checker（签名为definition、ProjectModel、project_id关键字，返回DomainReport）。缺checker会阻止验收就绪，不能只相信预存报告。输出为status（draft/generation_ready）、generation_ready、blockers及spec_content_hash。

所有DTO均为封闭dataclass JSON，未知/缺失键、类型或枚举错误拒绝。LocalWebSpec字段为schema_version、id、version、project_id、request_ref、source_ref、definition_ref、candidate_ref、review_ref、initial_project_ref、no_initial_data_reason、edit_scope、tasks、views、storage、access、evidence、acceptance_cases、confirmation_refs、required_unresolved、unsupported_requirements。schema_version固定local-project-web/0.1；edit_scope/storage/access允许null以保存草案，集合允许空但不会默认补配置。

嵌套字段：

|DTO|封闭字段|
|---|---|
|EditScope|entities、fields、relations（稳定ID数组）|
|WebTask|id、action（edit/check/save/load）、view_id|
|WebView|id、title、entities、fields、relations|
|LocalStorage|kind=local_json、relative_path、retention=retain_all_versions|
|LocalAccess|bind=127.0.0.1、audience=single_local_user、credential=session_token、allowed_actions|
|ConfigEvidence|area、ref、quote、reason|
|ExpectedOutcome|obligation、target、status（satisfied/violated/unknown/not_applicable/error）|
|PublicAcceptance|ref、description、public、steps、project、expected_outcomes|

ConfigEvidence.area须覆盖initial_project/edit_scope/tasks/views/storage/access/acceptance七项，ref必须绑定原source或已记录用户动作，quote为该来源全文或动作原文本，reason非空。来源hash和文字匹配只是归属核验，不推断自然语言真的支持某配置。配置整体另须用户显式确认，不能以自动解析或工程样例当真实需求授权。

就绪门槛包括：五个request/source/definition/candidate/review引用与当前审阅匹配、候选合法、当前候选无未决issues或required residual、无required_unresolved/unsupported_requirements。initial_project_ref必须是当前候选下实际保存的实例，或显式无初始数据理由；不可兼填。编辑范围/字段归属/关系端点和视图完整对应；四动作均有显式task和access授权。不提供默认权限、默认存储或业务操作。

storage路径为非空规范相对POSIX路径、以.json结尾，拒绝绝对路径、..、空段、反斜杠、冒号、控制字符、Windows保留名及特殊路径字符。生成/运行消费者还负责在选定输出根下核对解析后路径、拒绝symlink/junction、保留所有权与实际文件hash，不能因本静态检查省略运行时保护。session_token表示本机进程生成的会话凭据策略，spec不保存密钥；本合同无公网多用户认证。

每个公开验收用例ref.content_hash必须等于acceptance_digest(case)，该摘要覆盖除ref外的所有字段；同artifact_id/revision不能重复。steps精确为edit/check/save/load；expected_outcomes非空，并须与实际检查器返回的完整obligation/target/status序列相等，不能丢弃unknown或error行。public=false、错hash/定义/实际结果均阻止生成。此检查验证有限规则预期，E仍须实际执行编辑、检查、保存与重启读取的应用验收，不把checker通过当UI通过。

公开用例至少一个必须实际成功：完整population、无required residual，所有检查结果为satisfied或按合同保留的not_applicable，不得仅有violated/unknown/error失败样例。其余显式反例仍可保留原结果。initial_project_ref非空时也调用同一注入checker；非法结构、violated/unknown/error、不完整population均阻止generation_ready，不仅核对已登记引用。没有checker则不宣称初始实例或验收已验证。

## 显式确认及保存

先完整形成spec，再调用`spec_content_hash(spec)`。用户明确接受后，通过旧ReviewAction记录kind=confirm、targets=(WHOLE_CANDIDATE,)、text精确为`approve-local-web-spec:`加该hash。读取新review_ref，将回执action_ref放入spec.confirmation_refs。content hash仅排除review_ref和confirmation_refs以消除确认循环，覆盖其他全部配置、来源、版本和验收；普通“看过候选”确认不能替代规格确认。任何配置修改要求重新明确确认。

[apps/application_spec.py](../apps/application_spec.py)提供`save_spec(project_dir, spec, expected_spec_ref=None)`与`read_spec(project_dir)`。首次保存expected为null；更新须带当前spec_ref且使用新spec.version，保留旧版本/parent_ref。相同完整当前载荷already_recorded；错head/重复版本冲突。保存前核对当前review绑定，草案可保存；读取会重新检查当前review，旧绑定显示draft及blockers，不返回旧ready缓存。

单目录application-spec.json沿用审阅写锁，并有独立.application-spec.pending；flush/fsync/原子replace/读验完成才recorded。失败保留pending阻止继续；损坏/截断corrupt，忙锁busy，未知结果不伪装保存。最多32版本、24MiB存储、单spec2MiB、32task/view、16验收、64来源项，不裁剪历史。没有数据库或通用事件框架。

```text
python -B -I apps/application_spec.py save --project-dir ABS_PROJECT --spec SPEC_JSON
python -B -I apps/application_spec.py show --project-dir ABS_PROJECT
```

更新加`--expected-spec-ref REF_JSON`。CLI错误退出2，草案成功保存退出0但assessment.generation_ready=false。generation_ready只适用于该有限profile、指定head和公开工程检查，不证明原文忠实、自动领域建模或F1/F2完成。
