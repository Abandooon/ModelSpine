# 候选载荷同批重放协议

当前交付：**供应商无关宿主 + caller-supplied payload 重放，离线工程验收已通过**。基线63504a5。本轮没有真实传输适配器、provider配置、HTTP请求、timeout/服务错误执行或真实API/token/费用结果。完整后端仍缺用户指定的供应商、模型、端点、凭据环境变量名与可执行预算。未来真实接入约束见[候选后端合同](../../docs/candidate-backend-contract.md)；不得用本批工程fixture顶替一次真实请求。

## 固定范围与输入

限定一个已有公开structural-graph任务、同一个有序候选载荷、三个条件：terminal-only、dag-construction、ordinary-rule。当前不执行后端请求；未来配置就绪后才允许在同一计划下最多一次真实请求并共享其响应。三个重放条件不是三次API采样，不用于推断生成质量、提示效果或元模型组织优势。

| 内容 | 本批工程输入 |
|---|---|
| 任务与目标 | 既有structural-graph-task@1：DAG、a可达c、c不可达a |
| 基准 | 既有a→b→c扁平DAG，初始模型已经满足目标；本例是寻找合法编辑，不称修复坏模型 |
| 完整目录 | 只重定向edge-bc，source/destination各为a/b/c，共9项；ID与端点可见，没有答案/检查结果标签 |
| 搜索预算 | 原space.max_options=9，不覆写原输入或同版本字节 |
| 响应上限 | 工程request的max_returned_options=3；允许空列表，严格保留载荷顺序 |
| 独立验收 | 既有graph-reference.json/reference-index与测试侧task_oracle；调用app前核对task_ref |

本批的9次control预算与最多3个提议不会单独产生预算耗尽；相关宿主预算路径由A工程验收处理，不为制造差异事后改预算。请求/响应字节上限是宿主资源限制，不能当成provider token或费用硬上限。所有测试载荷明确为工程fixture，不能称真实供应商响应。

## 当前已实现的边界

A的`apps/candidate_batch.py`提供：

- `CandidateLimits(max_catalog_options, max_returned_options, max_request_bytes, max_response_bytes)`。
- `prepare_candidate_request(inputs, source_contents, request_id=..., limits=...) -> CandidateRequest`：完整任务/模型/元模型/空间、核验后的来源片段、无标签选项目录。
- `parse_candidate_selection(request, response_bytes) -> CandidateSelection`：严格JSON、请求身份与目录成员检查；保存request_hash、原文本/hash、有序ID及选项hash。
- `run_candidate_selection(inputs, request, selection, controller=None, construction_plan=None) -> CandidateBatchRun`：每次从相同base建立独立kernel；`.app_result`为原BoundedTaskRun，外层字段为`.exhaustion_scope='backend_batch'`。

B的[replay_candidates.py](replay_candidates.py)提供：

```text
replay_candidates(inputs, request, payload_bytes, expected_request_hash, *, checkpoint=None)
```

`expected_request_hash`必须由调用者从原先固定的请求证据取得，且等于digest(request)。不能看到载荷后重建request并称它是原始发送事实；这个相等检查也不证明请求曾通过网络发送。独立参考固定使用single.reference_spec，必须与inputs及request的task_ref一致。严格响应校验只调用A解析器，不在研究层另做生产解析或修正坏项。

旧observe_trial仅增加默认兼容的`execute_app=None`。回调签名与execute_condition一致，返回BoundedTaskRun，在原app异常捕获及真实checker计数包装内调用一次。默认仍执行原完整目录；新的重放闭包调用A公有run_candidate_selection并返回`.app_result`，不调用生产私有步骤或复制接受流程。原result_sink仍位于app checkpoint之后、捕获之外。

DAG条件省略controller/plan；另两组复用现有control_plan/ordinary_control，普通Kahn规则不依赖DAG控制器。三个条件使用同一个inputs/request/selection，保留有序子序列，各自从原base执行一次。没有先运行默认DAG再额外重放三次，也不把前一条件accepted传给下一条件。宿主重复校验selection不构成额外batch或API调用。

## 记录与分母

当前记录明确`payload_origin=caller_supplied`。只能证明重放期间`api_calls_during_replay=0`、`api_cost_during_replay=0`；原生成的source_generation_usage/cost为null并写明无法由载荷建立。provider/model/backend_receipt为null，不设伪backend=returned，不推断原载荷免费生成。测试作者可称其测试字节为engineering fixture，库不据此推断所有调用方载荷的来源。

外层预先保存1个planned batch及完整3个planned条件。分别记录valid_batches、started/terminal/not_started、app_returned、saved、reference_error_trials；这些字段不能合成一个success。非法载荷returned_options=null，合法空列表returned_options=0且valid_batches=1。条件条目引用同一batch request/response hash，只有一份完整app结果，不复制原生成用量或费用。

每条实际执行保留原observe_trial的步骤、status/reason、真实checker次数、app_result、reference结果/异常。继承字段llm_calls/paid_api_cost在新重放记录中改为明确的during_replay名称，避免把局部零调用/零API费用误读为原生成成本。人工时间、计算费用未测仍为null+原因。每条件wall_seconds包含完整app与包装执行，reference_seconds分开，沿用原计时边界。

## 检查点和失败

顺序为：完整计划与原始payload → 请求hash/参考绑定及解析 → 固定selection → 三条件隔离执行 → 汇总。

原payload在任何解析和app执行前按base64、字节长度、SHA-256进入checkpoint，包括非UTF-8字节。绑定/参考/解析失败时run_status=error，valid_batches=0，三个条件均not_started并保留原因；原始字节不丢弃，不执行部分批次或回退枚举。只有A的严格解析器判断载荷合法，目录内自环不是解析错误。

有效空列表仍真实调用三次空search，各自返回exhausted/no commit，`exhaustion_scope=backend_batch`；非空批次耗尽也不声称完整9项目录无解或representation_gap。原搜索reason不重写，budget_exhausted仍表示预算停止。

每个app返回后、任何参考调用前先checkpoint保存事实和真实CandidateBatchRun元数据。一个app异常不跳过其他条件：原base上的剩余条件仍执行一次；没有返回app收据时saved=null，不推断回滚。参考各固定角色只评价一次，异常与保存分开：真实commit已返回时，参考失败后saved仍为true，不反馈生成或重试。

checkpoint回调必须原子持久化或抛异常；可复用single._write_checkpoint。记录失败立即传播并停止，最后有效记录保留已完成条目、当前active app以及全部planned条件。真实临时目录测试验证了后续序列化失败后保留前一完成save及当前active/pending save；旧有效JSON保持in_progress，不能冒称全批完成。调用者负责排他创建输出路径，库无CLI/文件路径管理；`checkpoint=None`仅返回内存记录，不能声称已持久化。

## 当前验收与收尾

[test_candidate_replay.py](../../tests/test_candidate_replay.py) **11/11通过**：三次隔离真实保存及6/5/5 checker调用；重排/子序列；三个真实空search；非UTF-8原字节及三个未启动；原请求hash/同模型错task参考拒绝；单条件app错误后继续其他组；参考异常保留3个save且10个固定评价角色各调用一次；初始checkpoint失败阻止parser/app；后续序列化失败保留完成及active保存；execute_app默认兼容。原study **20/20**、multitask **13/13**同时通过，未修改旧测试。

A宿主负责严格JSON和输入绑定的全部边界，B不重复一套解析器。没有增加图样例、通用collector、网络函数、后端占位对象或正式pilot；旧265项和既有运行保持历史身份，不能沿用成此变更的全套验收。A统一最终full suite、共享artifact检查、维护及提交发布。

## 真实后端仍待完成的部分

用户尚未回复provider/model/端点/认证env变量名/预算。真实输入发送范围、提示/模型/采样版本、严格载荷提取规则、超时能力、token上限和费用依据须先固定；当前不默认选择，不发送数据，不造receipt或价格。

未来一次真实调用应在传输前保存计划和实际可见请求，在解析/重放前先保存原始响应与真实收据。逻辑请求只计一次，三个重放共享真实receipt，不能重复计费或当作三个独立样本。实际timeout、transport/service错误和是否已计费必须按收据记录，无重试、模型切换或坏载荷修复。缺用量/费率时为null+原因；字节估算不是token/货币硬上限。

这些真实HTTP、timeout与费用路径**本轮没有实现或验收**。配置到达后需另作对应实现和真实证据采集；无论一次请求得到空、错、失败或成功，都保留分母，不追加调用/图任务追逐优势。当前host与caller-supplied replay已可工程交付，完整真实候选后端仍未闭环，研究比较优势未证明。
