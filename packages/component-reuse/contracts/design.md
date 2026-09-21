# 外部能力接入目标合同

状态：draft，2026-09-21；运行模块仍 planned。[v0.1](v0.1/README.md) 的具体业务例仅为历史样例。本能力服务多个方向，不预设独立论文或组件市场。

输入：外部模型/代码/库/API 的 ArtifactRef、版本/来源/许可描述、目标义务与环境限制。拥有 CapabilityProfile、CompatibilityReport、AdaptationProposal；依赖 protocols/assurance；消费者为编排/implementation，事实可供 requirements/code-intelligence 使用。

## 操作与对象

- inspect(source_ref,scope) → CapabilityProfile：接口/类型/行为、观测证据、来源声明、假设及未覆盖范围分开记录。只读检查，不安装或执行任意外部代码。
- match(profile,obligations,environment) → CompatibilityReport：逐义务判定、类型/单位/协议/状态/版本差距、证据与残余。不以名称或向量相似度直接判兼容。
- plan_adoption(report,base,ownership) → AdaptationProposal：固定组件版本、模型提案、适配文件、迁移/检查义务、权限与失败回退限制。不直接提交模型或改第三方文件。

外部描述中的声明不是观测事实；缺省能力、缺失版本或无法访问来源不得被填为支持。接口形状匹配不能替代行为与时序协议。工具执行或访问要求交编排显式处理，不暗中扩大权限。

## 版本、失败与验收

源版本/哈希、目标义务/模型版本、检查器/环境共同绑定报告。版本变化须重检相关结论；保留仍可证明适用的局部证据。版本不匹配 conflict，访问/解析失败 error，不支持格式 unsupported，缺证据 unknown，确认行为不相容 violated。

A：候选能力与目标语义分开表达，匹配只产候选。B：版本升级/类型单位/行为前提变化使相应旧采用依据失效。C：外部实现与目标不符时明确适配或拒绝，无自动降级/安装/覆盖第三方文件。

实际提取代码前建立依赖闭包和来源映射；完整旧框架可运行不是本能力启动前提。采用后的真实构建及运行验收归 implementation/assurance，不能用匹配报告代替。
