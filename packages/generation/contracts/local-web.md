# 有限本机 Web 模板合同

`modelspine_generation.local_web` 拥有 local-project-web-template/0.1 的确定性计划和静态页面渲染。消费 A 的 `LocalWebSpec`、保存的 spec_ref、宿主重放核验的当前 review 以及显式 checker；调用 `assess_application`，draft 一律拒绝。plan 绑定全部规格、定义、初始实例、审阅摘要及来源引用；它不写文件，也不生成领域 Operation/Policy。

render 只把显式 views 的标题/ID输出为转义文本；浏览器完整 ProjectModel 始终是字符串。按钮来自显式 tasks；服务端重新核对 task、view、编辑范围、数据版本和全部有限义务。模板不生成规则求值器，不在 JS 中重建 Int64。静态页面只是候选文件，尚非通过交付验收。

本目标的额外可执行条件归 implementation：至少一个 view 覆盖整个 edit_scope 且具有 edit/check/save/load 四动作，并至少一条公开成功例通过运行时相同的范围与版本预检。跨视图组合事务 unsupported，不削弱 A 的通用规格合同。公开 checker 预期、目标路径预检、真实 HTTP/浏览器业务验收分开报告。

当前模板服务于本机 ProjectModel 编辑/检查/保存/读取，不推导域权限、集成、后台业务或未决需求。生成目标是明确选择，不是 BESSER 失败的自动降级。完整使用入口见 [local-web](../../../docs/local-web.md)。
