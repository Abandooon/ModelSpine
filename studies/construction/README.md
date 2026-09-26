# 有限构造机制工程先导

当前使用[多任务与两阶段协议](multitask-protocol.md)，入口为 `python -B studies/construction/run_multitask.py --output studies/construction/runs/<new-unique-name>.json`。固定三类拓扑任务、一个依赖后继和一个初始成环边界，共15个计划条目；阶段1只执行一次，不把阶段或条件当作独立项目。每条件从自己的真实accepted进入阶段2，保留全部父目标，只追加预先固定的d→c可达目标。参考在执行前核对任务身份，后继参考保留模板来源并使用独立派生版本。

完整回归 **265/265** 通过后，统一采集[本轮正式运行](runs/2026-09-26T173726308106Z.json)：15计划/启动/终态，12 app返回，9保存且独立验收均满足；3空间耗尽，3不支持成环初始状态错误（实际code=invalid），无参考错误。三条件各完成真实revision1→2；运行93项来源哈希前后一致。fork两个阶段搜索检查各为仅终验4次、两前控各2次；diamond 2/1/1，disconnected 3/1/1。成功接纳另各3次检查。DAG和普通Kahn仍为零差异；单图有限空间复用不证明元模型组织优势。人工首次/增量时间和计算费用仍未计量。原始输出见同前缀`.pilot.stdout.txt`/`.pilot.stderr.txt`，命令身份见同前缀`.execution.json`。

新验收见 [test_construction_multitask.py](../../tests/test_construction_multitask.py)，固定答案见 [semantics.json](../../tests/fixtures/construction/multitask/semantics.json)。原普通Kahn规则跨任务参数化复用，没有逐任务控制分支。新增记录使用旧 observe_trial 的可选真实结果回调与原子检查点，不另建提交流程。下文均为此前单任务运行的历史说明，原始runs未修改。

本目录实际装配三个可运行条件：terminal-only、DAG construction + terminal、ordinary-rule + terminal。它们使用同一个固定任务、端点选项、顺序、预算、构造器、终验与 kernel 保存入口。普通程序以 Kahn 拓扑消除独立判环，不调用 DAG 控制器。[协议](protocol.md)在集成前固定目标、九选项答案、21 对照执行与 3 故障探针。

独立验收复用测试侧 task_oracle 和既有固定 graph-reference；只在 app 返回后评价各候选和已保存模型。基础模型本已满足路径任务，本例探索合法的实际端点变更。有限选项及不同预算不是独立统计样本；没有 LLM、真人或方法优势结论。

从 platform 运行：

```text
python -B studies/construction/run.py --output studies/construction/runs/<new-unique-name>.json
python -B -m unittest discover -s tests -p test_construction_study.py -v
```

输出以独占创建保留，拒绝覆盖历史记录。每条执行含 planned/started/终态、完整 app 结果、每步前置判定/候选终验、独立评价及保存事实；异常保留类型和原因，无返回轨迹时步骤计数为 null。预算不足、空间耗尽、unknown/error 全部入分母，故障注入单列。

`search_candidate_checks` 仅表示搜索候选检查；研究侧透明包装原检查器，实测 `total_development_checker_calls`，差值得到最终接纳检查次数。成功保存现经 assess_task、kernel.decide、kernel.apply 共 3 次额外调用。`wall_seconds` 包含条件装配、包装开销及完整 app 执行，在返回或抛异常后立即截止；`reference_seconds` 单独计，不将序列化纳入前者。LLM 调用与其 API 费用为 0；人工和计算费用未计量，均为 null 并附原因。墙钟为单次工程测量，不是性能结论。

工程反例和诊断见证见 [test_construction_study.py](../../tests/test_construction_study.py)；固定来源与关联预设在 [diagnostic-cases.json](../../tests/fixtures/construction/diagnostic-cases.json)。测试重放同元模型下的修正/新增见证，明确有可行行为修复不等于能区分 mapping_error/model_gap；没有生产诊断器，也没有 representation_gap 的证明。

## 首轮真实记录（记录层修复前）

A 依赖边界修复完成后，B/C 定向测试 **13/13 通过**；[测试日志](runs/2026-09-26T161535942620Z.tests.stderr.txt)、[执行命令与退出码](runs/2026-09-26T161535942620Z.execution.json)均保留。测试与先导命令退出码均为 0。

[完整运行 JSON](runs/2026-09-26T161535942620Z.json)包含预定/启动/终态 **24/24/24**：21 条对照执行、3 条明确故障注入；23 条返回 app 结果，1 条抛异常。状态为 candidate_found 9、exhausted 6、budget_exhausted 6、unknown 1、error 2。9 次模型保存的独立参考全部满足；异常没有返回的保存状态保持 null。[stdout](runs/2026-09-26T161535942620Z.pilot.stdout.txt)及[stderr](runs/2026-09-26T161535942620Z.pilot.stderr.txt)原样保留，stderr 为空，预设故障详见 JSON。

| 预算 3 的条件 | considered | excluded | 构造/搜索候选检查 | 最终接纳检查 | 总检查调用 | 保存与独立验收 |
|---|---:|---:|---:|---:|---:|---|
| terminal-only | 3 | 0 | 3 | 3 | 6 | a→c，通过 |
| dag-construction | 3 | 1 | 2 | 3 | 5 | a→c，通过 |
| ordinary-rule | 3 | 1 | 2 | 3 | 5 | a→c，通过 |

三条件在预算 1/2 均 budget_exhausted，预算 3/9 均找到并保存同一 a→c；唯一正确编辑可达，只有非法编辑时 exhausted，原样选项不伪造候选/保存。每条件 7 条对照执行各考虑 12 次选项；总构造/搜索检查分别 11/6/6，额外接纳检查各 9，总检查调用 20/15/15。以上是固定单任务、重复预算场景内的工作量，不能当作独立样本或错误概率。

预算 3 完整调用墙钟分别约 0.0640/0.0554/0.0550 秒，参考评价分别约 0.00468/0.00342/0.00347 秒。单次测量含 Python 包装开销，不能推断性能优势。人工时间和计算费用未测。普通规则与 DAG 控制的九选项判定一致，这一工程结果不足以归因为元模型组织方法的优势。

运行基于 Git `d5834178e29186e408b1a7f9e171004804e30d59` 之上的未提交工作树；JSON 保留 dirty 状态与 50 个源码/输入文件哈希，运行前后及采集后核对一致。记录 SHA-256 为 `ce3a88c0d19c3f9084edd6b25b2f5356c5737e1328326b16edb40137aa3ae89d`。UTC 文件名对应北京时间 2026-09-27；原结果不随后续提交重写。

## 2026-09-27 记录层修复与新运行

审核发现：旧 runner 在 app 已保存模型后遇到参考评价异常会丢失该试次，整批结束前异常还可能留下空文件。新记录使用 `construction-pilot/0.2`，分别保存 app 的 `status/saved/app_result` 和 `reference_status/reference_errors`；每个既定候选、保存模型各评价一次，异常不驱动搜索或重试。参考执行异常退出 2，不把已保存模型改成回滚，也不把评价异常写成通过。

CLI 在 app 返回后、参考执行前及每条试次完成后写原子 JSON 检查点。后续采集或序列化失败保留最近有效记录及当前 `active_trial`，标记 `run_status=error` 并非零退出；已存在路径直接拒绝。完整字段语义与进程中断边界见[协议](protocol.md)。

新增 7 项回归覆盖候选/保存参考异常、检查点顺序、后续试次异常、序列化失败、拒绝覆盖和非零退出。study 定向验收 **20/20**，完整隔离套件 **241/241**（19/11/16/30/28/137）；真实临时目录验证已有记录和当前已保存 app 事实仍可解析。完整日志及 81 项源码/输入身份由研究工作区修复交接保存。

[新运行 JSON](runs/2026-09-26T164942482157Z.json)保留相同的 24 条计划与条件，计划/启动/终态为 **24/24/24**，app 返回 23 次、保存 9 次，状态数仍为 **9/6/6/1/2**；9 个保存模型的独立参考全部满足。此次正常先导没有参考执行异常，异常行为由上述故障回归验证。运行状态 complete、退出 0，详见[命令记录](runs/2026-09-26T164942482157Z.execution.json)、[stdout](runs/2026-09-26T164942482157Z.pilot.stdout.txt)及[stderr](runs/2026-09-26T164942482157Z.pilot.stderr.txt)。

新运行基于 `7a79824a3319c03fd8578d53b62597beb69566e6` 之上的未提交修复，50 项源码/输入哈希前后一致；记录 SHA-256 为 `2a1d5ae43a60c8c22cad82fa7920b66875a4481f99c88eb172e6946d89b8778c`。旧运行及其原始日志保持原字节。条件、参考规格、生产接口与研究结论均未改变，仍未证明比较优势。
