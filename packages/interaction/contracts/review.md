# 有限候选审阅呈现合同

本实现消费 [A 的 model-review/0.1](../../requirements/contracts/review.md)，只拥有呈现和浏览器内草稿。状态、重放、检查、保存与回执均归 A；不引入另一份审阅状态机。完整交互设计仍见 [design.md](design.md)。

`modelspine_interaction.review_ui` 提供：

- `project_review(view) -> list[dict]`：将 A 已核验视图投影成纯文本、表头、表格行和完整详情文本；不修改输入、不做合法性或表达式求值判断。
- `format_expression(expr) -> str`：只格式化已通过 A 检查的 finite 语法；二元表达式全加括号，保留 AND/OR/IMPLIES、field/count 方向、适用/断言/例外，Python 格式化保留 Int64 精度。不是求值器。
- `review_page(token) -> str`、`review_asset(name) -> bytes`：固定页面及封闭的 JS/CSS 资源。token 属性转义；候选、原文、用户文本仅经 textContent/createTextNode 渲染，无 innerHTML。

主视图包含术语/字段及类型、必填/可空、关系名称及端点/双向基数、规则上下文与三个独立谓词、问题/残余和动作状态。完整 JSON、原响应文本/精确 base64、来源和身份引用保留在展开详情。非法候选不猜测合法结构，仍展示原件和诊断。无候选结构不是检查通过。

精确显示依据为服务器产生的 `presentation` 字符串与原件，而不是浏览器解析后 `view` 中的数值。JavaScript Number 会舍入超出安全整数范围的 Int64；前端不得据此重建表达式、完整详情或候选。服务器先用 Python 对原始核验视图格式化规则和 JSON 详情，再作为字符串传输；原响应字符串/base64独立保留精确字节。无需改变 A DTO 或引入另一套 JSON 框架。

应用 `apps/model_review_ui.py` 装配 A 的 `create_review/read_review/submit_action` 和公共 `ReviewAction`。本包仅导入标准库，当前 `runtime_dependencies=[]`；公开视图的设计依赖不伪报为 Python 导入。应用直接添加本包 src 路径，bootstrap 未改，后续统一登记由总领负责。

浏览器每次载入固定 `request_ref/candidate_ref/review_ref/question_ref`，四种动作直接构造公共载荷。`review:candidate` 为整体原件，`$candidate` 为合法同名元素。actor 在启动时固定，只是归属，不是认证。每次提交生成独立动作 ID；没有后台重试、自动换版本或合并。收到真实 recorded/already_recorded 回执才显示已记录；保存后页面仍绑定原版本，用户显式从新窗口读取最新记录继续。旧页冲突、读写失败和网络无回执均显示错误并保留输入；可能已落盘但丢失回执时要求重开核验。草稿只存页面内存，关闭页面不保留草稿；再次打开恢复的是 A 已保存记录。

answer/decline 保留 unresolved；confirm 不改变检查和候选；propose_edit 提交完整 UTF-8 候选文本（可非法），检查和 adoption=pending 由 A 返回，提案不覆盖原候选。取消只重置当前表单，布局仅切换 CSS，不产生动作。当前不支持 ProjectModel 实例、提案采纳、自动修订、新候选生成或 ApplicationSpec/应用生成；用户页面以行为语言说明限制。

服务只监听 `127.0.0.1`，一个进程绑定一个显式已存在绝对目录，不接受 URL/请求目录选择。精确 Host、Origin、Fetch-Metadata（存在时）和随机页面动作能力串约束请求；API 读取也须能力串；POST 必须同源、JSON、单一长度且不超过 512 KiB，拒绝重复边界头/Transfer-Encoding，连接读超时 10 秒。资源路由封闭，未知方法不调用存储，CSP 禁止内联脚本/嵌入，响应 no-store。不是认证系统、多租户隔离或防本地恶意进程方案。A 独占管理目录校验、锁和写入；失败不抢锁、不修复、不回旧缓存。

验证范围见 [启动和验收说明](../../../docs/model-review-ui.md)。工程样例和浏览器自动化只验证有限 UI，不证明意图忠实性、真实语言链或 F1/F2 完成。
