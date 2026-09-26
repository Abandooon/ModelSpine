# 有限构造机制工程先导

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

## 本轮真实记录

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
