# 本地候选审阅 UI

本入口读取本地已保存的审阅项目，展示原文、术语/字段、关系、规则、问题、残余、诊断和用户记录；不要求生成任何应用代码。

从 `platform/` 启动（Python 3.10+，标准库，无 npm/Web 框架安装）：

```text
python -B -I apps/model_review_ui.py --project-dir "E:/absolute/existing-review-project"
```

浏览器打开终端输出的 `http://127.0.0.1:随机端口`。可用 `--port 8765` 指定本机端口、`--actor "用户归属名称"` 标记操作者；该名称不是登录认证。Ctrl+C 停止。服务只接受启动时指定的一个绝对目录，页面不能选择其他磁盘目录。

已有目录必须由 [A 的审阅入口](model-review.md) 保存过会话。首次创建可在显式已存在空目录上直接装配 A 接口：

```text
python -B -I apps/model_review_ui.py --project-dir "E:/absolute/empty-project" --request "request.json" --candidate "candidate.raw" --session-id "review-1"
```

三项创建参数须齐全；已有会话拒绝覆盖。request 必须是 A 的 ModelingRequest，candidate 是外部原始响应字节，非法候选也可审阅。此入口不调用语言模型、不自动生成示例作为缺失真实输入的替代。

页面先显示简要版本和独立状态；术语/字段表标明类型与必填/可空，关系显示端点名称及双向基数，规则分别展示上下文、适用、断言、例外。表达式只格式化、不求值；AND/OR 组合保留括号。完整 JSON、来源、精确引用及原件在详情中。非法原件保持可见并展示诊断。精确显示使用服务器 presentation 字符串和原件，前端不得从已解析 view 的 JS Number 重建表达式、详情或候选，以免 Int64 舍入。

可答复/拒答、勾选明确目标确认、提交完整 UTF-8 候选文本及修改理由。`review:candidate` 的整体确认与 `$candidate` 元素确认分开列出。仅收到持久化回执才显示“已记录”，不显示“已修订/已接受”。保存后从页首链接在新窗口读取最新记录继续，旧页及未提交输入保留；旧页再次提交会产生明确版本冲突，不自动换版本重发。取消清空本表单，不提交；布局切换不写语义。草稿只保存在当前页面，保存过的记录才可重开恢复。

本版没有实例查看、提案采纳、回答驱动新候选或应用生成；形式检查、用户确认、修订 pending 和候选未变分别保留。遇 busy、incomplete_write、IO 或版本错误，先保留输入和错误再从新窗口核验；不自动删锁/pending 或回滚。能力串、Host/Origin 校验仅减少本地误写和恶意网页写入，不是完整认证或多租户保护。

维护者验证：

```text
python -B -I packages/interaction/tests/test_review_ui.py
python -B -I tests/test_model_review_ui.py
```

2026-09-30：3 项呈现单测、6 项 HTTP 测试通过；使用已安装 Edge 154.0.4258.37 和捆绑 Playwright 实跑 10 组浏览器行为，包括恶意 HTML 纯文本、AND/OR/例外、取消/布局、答复拒答、局部/整体确认消歧、非法提案、旧窗口冲突、锁失败、注入 replace 失败与恢复读取。无浏览器下载或运行时新增依赖。工程输入统一标记 `hand_authored_engineering_only`；不是用户可用性研究、真实语言结果或 F1/F2 阶段验收。研究工作区的本批交接和独立运行证据由集成负责人保管，平台不嵌入私人研究材料。
