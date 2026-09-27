# 原文领域建模入口

当前完成原文输入与候选合同消费者：可准备请求、导出语言模型提示、核对外部候选；新增有限类型化定义及实例规则检查。真实语言模型传输、从原文自动抽取和回答驱动修订仍未实现。既有有限澄清与图构造入口保留各自范围，不作为本入口的前置条件。

2026-09-28新增[finite-domain/0.1合同](../packages/protocols/contracts/finite-domain-0.1.md)、[完整语言设计](../packages/protocols/contracts/language-0.2.md)及[消费者设计](../packages/protocols/contracts/consumers-0.2.md)。公开[工程正/反/未知/残余样例](../packages/protocols/contracts/finite-domain-examples.json)可供一次来源投影试验；样例为人工构造，不是自然语言或独立语义验收。

```text
python -B -I apps/domain_modeling.py typed-prompt --request request.json --output typed-prompt.txt
python -B -I apps/domain_modeling.py typed-inspect --request request.json --response typed-response.json
python -B -I apps/domain_modeling.py check-project --request request.json --response typed-response.json --project-model project.json
```

新增命令保持来源/请求绑定和不覆盖输出。check-project在三标量/二元关系/有限表达式配置内真正执行检查，报告逐项satisfied/violated/unknown/error/not_applicable；退出0仅表示报告已完成，不代表所有义务通过。原R1 prompt/inspect仍只执行原合同。typed-response必须提供全部元素引文，不能直接把独立样例或参考答案当作模型输出。真实API配置仍缺，平台实验调用为0；不选择默认供应商/模型、不模拟自然语言成功。

从仓库根运行，source.txt 是你提供的 UTF-8 需求原文：

```text
python -B -I apps/domain_modeling.py prepare --source source.txt --project demo --source-id requirements --source-version 1 --request-id request-1 --scope "建立原文涉及的概念、属性、关系与约束候选，保留歧义" --output request.json
python -B -I apps/domain_modeling.py prompt --request request.json --output prompt.txt
```

第一条只需要原文及身份、范围，不需要正确元模型、模型实例或候选目录。第二条导出固定方法指令和原文，不发送网络请求；prompt.txt 不是生成结果。改变来源内容、版本或任务范围后应准备新请求，旧响应不能继续绑定。

当明确获得符合合同的外部候选文件时，可以核对：

```text
python -B -I apps/domain_modeling.py inspect --request request.json --response candidate.json --output inspection.json
```

本命令不会生成 candidate.json，也不会自动填入示例答案。inspection.json 将候选标为 unconfirmed，来源定位与结构检查通过仅返回 structure=valid；semantics=not_checked、rule_execution=not_implemented、generation_provenance=not_verified、model_committed=false。退出 0 的含义只是本次检查完成，错误退出 2。输出文件采用排他创建，重复路径报错并保留旧文件。

领域候选包含概念、属性、带端点和双向基数的关系、原文规则，以及歧义/冲突/缺失/不支持项。未知、零、无上限分别表达；条件规则不压缩成无条件关系。完整字段、证据行号、载荷限制和失败语义见[原文候选合同](../packages/requirements/contracts/domain-modeling.md)。

[五段独立开发原文](../tests/fixtures/domain-modeling/README.md)及其语义期待用于后续人工/独立评价。可以显式选择 sources 中某段原文作为输入；expectations.json 只能在评价侧读取，不能放入生成提示或作为方法的答案目录。手工候选的合同测试不构成自然语言抽取的成绩。

下一步是选择并配置一个真实语言适配器，按固定模型/端点/预算读取该请求并保留真实响应与失败；无配置时如实停留在输入和候选合同阶段，不返回模拟生成结果。
