# 业务实现与应用交付

保留S1设计合同；现提供[单一本机Web交付切片](contracts/local-web.md)：将确定性计划物化到新目录，实际构建/启动，执行完整实例的规则检查、显式保存及重启读取。新目录更新核对旧文件及人工文件、重检数据并保留旧版；迁移、自动回滚和崩溃恢复不支持。独立制品只需Python标准库，见[生成与更新说明](../../docs/local-web.md)。

状态、依赖和证据由 [module.json](module.json) 维护。公开字段与错误/副作用/版本语义见 [合同](contracts/v0.1/README.md)，正反例见 [结构化样例](contracts/v0.1/examples.json)。共享结构只有 [protocols](../protocols/contracts/v0.1/README.md) 一处定义。

工程验收不是论文比较实验；未实现范围保持设计状态，未知不算通过。运行包不导入论文、实验或旧工作树。
