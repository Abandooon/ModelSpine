# 给D：有限审阅接口 model-review/0.1

输入ModelingRequest与外部typed候选原字节，输出可恢复审阅视图和动作回执。无需真实LLM或已接受模型；本profile无实例输入/检查、提案采纳、自动修订、UI、服务器或认证。完整[合同及失败责任](../packages/requirements/contracts/review.md)；以下函数位于[apps/model_review.py](../apps/model_review.py)，共享动作直接导入`modelspine_protocols.review`。

|函数|输入→输出|
|---|---|
|create_review|显式已存在绝对project_dir、request、candidate_raw:bytes、session_id关键字→初始视图；已有会话拒绝覆盖|
|read_review|project_dir、可选expected_review_ref:ArtifactRef→核验后的视图；截断/错hash不回旧缓存|
|submit_action|project_dir、ReviewAction→已持久化receipt；失败抛错，无recorded|

视图读terms（实体/字段）、relations、rules、residuals、issues、traces、questions、inspection.diagnostics、actions/proposals/confirmations。非法AST也有原件candidate_base64、仅供显示candidate_text及诊断问题；空结构数组不表示检查通过。candidate_text使用UTF-8 replacement，身份/原件以base64解码字节为准。所有文本作为数据转义呈现。source_text是原文；动作actor/text是宿主提供的归属/用户修改来源，不是认证身份，也不合并为原文SourceSpan。

从当前视图构造回答（不预置答案选项）：

```python
from model_review import read_review, submit_action
from modelspine_protocols import ArtifactRef, decode
from modelspine_protocols.review import ReviewAction, WHOLE_CANDIDATE

v = read_review(project_dir)
a = ReviewAction(
    schema_version="model-review/0.1", id="client-action-unique-id", project_id=v["project_id"],
    request_ref=decode(ArtifactRef, v["request_ref"]),
    candidate_ref=decode(ArtifactRef, v["candidate_ref"]),
    expected_review_ref=decode(ArtifactRef, v["review_ref"]),
    question_ref=decode(ArtifactRef, v["questions"][0]["ref"]),
    actor="host-provided-actor", kind="answer", text=user_answer,
    targets=(), proposal_base64=None)
receipt = submit_action(project_dir, a)
```

- decline沿用问题绑定，text可空；空白answer非法，“不知道”可记录但仍unresolved。
- confirm使用question_ref=None、targets=(稳定元素ID,)，或整体targets=(WHOLE_CANDIDATE,)；常量为`review:candidate`，合法`$candidate`仅表示同名元素。确认不清未决、不改变检查。
- propose_edit仅支持完整候选原字节：question_ref=None、targets=()、proposal_base64=base64.b64encode(raw).decode("ascii")、text为修改理由。合法/非法提案均留档/检查并待采纳，不替换当前候选；可提出移除规则/residual或改AND/OR，来源留痕不等于意图正确。

candidate_ref绑定响应字节，不能拿definition_ref代替。动作同时绑定独立review_ref：candidate没变时旧窗口也conflict。相同ID完全相同载荷重试already_recorded，不追加版本；recorded_review_ref是首次结果、review_ref是当前版本。异内容同ID冲突。next_candidate_ref始终null；回答/编辑revision_status=pending，真实自动修订not_run。重新read后才构造下一个新动作。完整草案的view_ref/actor_ref等字段不能混入本profile，精确映射见合同。

错误：ContractError的invalid/unsupported/conflict/corrupt/busy/incomplete_write分别为非法、超范围、绑定/版本冲突、存储损坏、锁占用、未完成写入；OSError为真实IO失败。D显示错误并保留用户输入，不静默换ID重试或回旧缓存。宿主独占管理本地目录，残留锁/pending保留证据后人工诊断；本版不自动抢锁、修复或回滚。revision_status=pending是语义待修订，与磁盘incomplete_write不同。已有head时传给read_review可拒绝旧文件；无外部锚无法识别恶意完整回滚。

工程演示：显式新建空目录后，从platform运行：

```text
python -B -I apps/model_review.py demo --project-dir ABSOLUTE_EMPTY_DIRECTORY
python -B -I apps/model_review.py show --project-dir ABSOLUTE_EMPTY_DIRECTORY
```

demo为人工工程原文/候选，保存一次未知回答并重开，输出API调用0、pending和原候选身份，不是自然语言生成。真实输入用create的--request/--candidate/--session-id；act用--action读取严格JSON动作；每条命令都须--project-dir。完整UI、实例/提案采纳与真实自动修订仍待各自明确任务。
