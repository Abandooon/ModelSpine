# 固定多任务构造输入

本组是预先声明的小型工程任务，不是独立统计任务样本集或 LLM 实验。参考答案由 study 侧另行固定；这些目录只保存开发任务、来源、模型/元模型和允许编辑空间，不保存正确提案或下一阶段接受快照。具体比较与完整分母由 construction study 协议维护。

| 卡片 | 结构与固定目标 | 编辑边界 |
|---|---|---|
| [fork-stage1](fork-stage1/card.json) | 分叉图；a 可达 d、b 可达 d、c 不可达 d，保持 DAG | 重定向 edge-cd；6 个允许选项，控制预算 4 |
| [diamond](diamond/card.json) | 菱形图；a 可达 d、b 不可达 d、a 可达 b，保持 DAG | 重定向 edge-bd；4 个允许选项，预算 3 |
| [disconnected](disconnected/card.json) | 两个不连通分量；a 可达 d、c 可达 d、d 不可达 a，保持 DAG | 只允许在 a/b 内重定向 edge-ab；4 个选项，预算 4 |
| [fork-stage2](fork-stage2/card.json) | 原样保留阶段 1 全部声明/义务/绑定，新增 d 可达 c | 预先声明 edge-ac 的 4 个选项，预算 4；须先有真实父提交 |
| [unsupported-cycle](unsupported-cycle/card.json) | 初始成环，要求 DAG 及 a 可达 c | 当前保持 DAG 的构造适配器拒绝初始非法图，不替换算法 |

节点/边身份固定，重定向不改元素 ID。根成员依赖不声称完备，可编辑边依赖恰为旧端点且完备。选项按 edge/source/destination 字典序展开，控制预算包含排除和 no_change，准备成本不受该预算限制。

从 platform 运行一个初始卡：

```text
python -B -I apps/bounded_generation.py --case domain-packs/structural-graph/construction/multitask/fork-stage1/card.json
```

卡内各路径必须是卡目录内的相对路径；task/space/source 字节和引用在执行前固定。`load_construction_case` 返回既有五元组供 `run_construction` 使用。`fork-stage2` 是后继模板，不能作为独立初始卡执行；其 model/task.base/space.base 指向预先声明的父输入，用于核对来源和阶段关联。

`advance_construction(parent_inputs, actual_result, stage2_card)` 核对真实父提交与完整保留父义务后，只绑定实际 accepted 到下一基准，派生 task/space 新版本和哈希，重新准备任务。模板文件保持原字节，绑定后的完整任务和空间由研究运行记录。下一基准不能从文件内预制答案替代。此例以两次单边修改检验真实 revision 0→1→2，不提供持久化内核、联合多边搜索、任意工作流或元模型迁移。
