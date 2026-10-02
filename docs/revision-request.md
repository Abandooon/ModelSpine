# 离线回答修订请求 revision-context/0.1

此入口确定性整理原文、旧候选与用户回答/拒答，供未来明确接入语言装配；不调用模型、不生成或修补候选。它没有修改被冻结typed输入合同，也没有把回答塞回原文构造假来源。derived_modeling_request=null、generation_status=not_run、next_candidate_ref=null。

纯函数位于[requirements/revision_request.py](../packages/requirements/src/modelspine_requirements/revision_request.py)：`prepare_revision_request(session, expected_review_ref=..., action_refs=...)`。输入必须为可重放ReviewSession和精确当前head；action_refs为1–64个不重复、实际已记录answer/decline的action引用，可以包含历史候选的回答，每条保留其原parent_candidate/question/action/source绑定。未知回答不填默认，拒答原文本即使为空也独立保留，非回答动作或伪造引用拒绝。

封闭输出字段为ref、schema_version、review_session、action_refs、context、prompt。review_session保存可重放来源证据；context含parent_request_ref、parent_candidate_ref、parent_review_ref、original_source_ref/text、parent_candidate_base64、responses及未执行声明。每个response含原action、action_ref、question、该动作parent_candidate_ref/source_ref、provenance。它们是用户后续归属，不伪装SourceSpan，也不修改旧ModelingRequest。prompt保留原typed前缀并附明确的数据块/来源分离说明；不能直接冒称现有语言app已支持该信封。

`verify_revision_request(envelope)`以保存会话完整重放重新构造整个输出，核对head/问题/动作/原件/摘要和精确prompt。输出ref.content_hash覆盖除ref外的全部内容，同输入生成同字节；任一prompt/响应/来源篡改都会失败。非法原候选也可准备修订上下文，但仍保持非法原件和诊断，不变成合法替代。

[apps/revision_request.py](../apps/revision_request.py)提供`export_revision_request(project_dir, output_path, expected_review_ref=..., action_refs=...)`与`read_revision_request(path)`。目录和输出路径须显式绝对，源会话在原锁内读取；输出使用排他创建、fsync及重读验证，不覆盖已有文件，失败抛错且保留现场，不自动删文件或重试。24MiB上限，symlink/junction拒绝。actor仍为宿主归属而非认证。

```text
python -B -I apps/revision_request.py export --project-dir ABS_PROJECT --output ABS_NEW_FILE --bindings BINDINGS_JSON
python -B -I apps/revision_request.py show --output ABS_NEW_FILE
```

bindings封闭字段为expected_review_ref及action_refs，均为ArtifactRef JSON。错误退出2、不输出成功；本地工程演示明确hand_authored_engineering_only，API调用0。真实回答驱动自动候选仍not_run，不据此宣布F1/F2完成。
