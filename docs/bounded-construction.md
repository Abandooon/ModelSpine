# 固定目标下的有界构造控制

从仓库根运行 `python -B -I apps/bounded_generation.py`。工程输入复用固定结构图任务，从[编辑空间](../domain-packs/structural-graph/construction/space.json)允许的端点赋值构造提案，未提供完整候选模型或正确提案。它不是任意 DAG 生成器，也不修改任务目标。

默认只重定向 edge-bc，source/destination 可取 node-a、node-b、node-c，按字典序考虑，最多 9 个选项。a→a 在创建提案前因自环被排除；a→b 虽无环，完整终验发现 a 无法到达 c；a→c 满足全部固定目标，才经原有任务验收和 kernel 接受为 revision 1。保存为单实例内存提交，未产生应用文件。

## 分工与调用合同

`modelspine_generation.bounded.search(snapshot, task_ref, check_plan, construction_plan, options, max_options, control, build, evaluate)` 管理有界搜索。输入为事先固定的 `EditOption(id,target,values)` 元组；每次 control 调用消耗一个预算，包括 exclude/no_change。控制先于提案和候选创建；允许后才 build，然后由可信宿主 evaluate 真实预览和检查。

控制结果 `ConstructionDecision` 绑定选项哈希，状态为 allow/exclude/no_change/unknown/error。`CandidateEvaluation` 保留候选和完整 ValidationReport；`ConstructionStep` 保留每个已考虑选项及其决定、提案、评价。`ConstructionRun` 绑定 task_ref、base、GenerationPlan，停止为 candidate_found/exhausted/budget_exhausted/unknown/error。unknown/error 立即停止；异常传播，不自动换控制器或终验器。not_applicable 不作为满足，停止为 unknown。未变化选项不构造提案或伪造提交。

当前宿主预先物化完整笛卡尔编辑空间，core 在开始控制前核对全部选项；时间与内存随总选项数增长，即使预算为零也有准备成本。max_options 只限制控制调用，不是总时间或内存上限。当前工程消费者仅 9 项；更大空间的资源限制或惰性处理需另定合同和验收，当前未实现。

GenerationPlan 必须覆盖固定 CheckPlan 的所有义务及版本，声明 construction 或 terminal-only；residual 恰列未前置控制的义务。所有义务仍需终验，包括前置受控项。候选必须属于原项目/模型/元模型且 revision=base+1，报告须匹配实际候选、原计划、全部范围与义务。核心不重复执行领域语义：control/build 的领域正确性及 evaluate 的提案到候选语义属于可信宿主责任；完整性绑定不证明语义正确。

[dag_construction.py](../adapters/dag_construction.py) 解释 `DagEditSpace` 与 DAG 义务，`prepare_dag(...)` 返回 options/plan/control/build。初始图必须符合现有扁平 DAG 支持范围；固定允许边和端点必须属于该图，列表可为空。控制移除待编辑旧边后检查新目标是否可达新源，保留其他平行边；自环或回路被前置排除。builder 同步两个 SetProperty 与端点 SetDependencies，不偷偷执行前置规则，让明确的仅终验对照可复用相同构造器。根的成员依赖仍为 incomplete，不宣称解决全图增量证据完备性。

[bounded_generation.py](../apps/bounded_generation.py) 核对编辑空间原字节哈希、身份、任务与基准，装配真实 kernel.preview 和 check_tasks，再调用原有 run_task 接受候选。`run_construction(..., *, controller=None, construction_plan=None)` 只允许同时显式注入控制器和计划；builder、终验与保存流程固定。`BoundedTaskRun` 分开记录空间引用、搜索和最终 TaskRunResult；candidate_found 不等于已保存，保存以 run.commit 为准。CLI 成功保存退出 0，未保存退出 1，输入/合同错误退出 2。

## 验收与研究边界

可编辑边的原 dependencies 必须恰为旧端点且 dependencies_complete=True；额外依赖或不完整声明超出本次重定向支持，明确拒绝。这样端点更新不会静默删除其他语义依赖或提升完整性；未编辑边及图根沿用原声明。

包测试验证预算、停止、覆盖、错绑定与回调失败，适配器测试验证真实移除旧边、平行边、无变化与空间边界，应用测试验证来源身份及搜索通过后终验仍能拒绝。既有图/FSM/澄清验收保留。独立参考与三种确定性条件位于 [construction study](../studies/construction/README.md)，不被生产代码读取。

当前机制只建立一项关系义务的可运行前置控制。行为构造、LLM 候选、自动修复循环、一般表示不足诊断仍未实现。有限空间耗尽或预算耗尽不证明 representation_gap；同团队预定参考与刻意反例也不证明比较优势。
