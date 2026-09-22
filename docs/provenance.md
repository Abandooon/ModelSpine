# 来源与许可状态

本仓库按能力重新组织有限实现，没有整体集成旧框架。外部来源材料与来源审计在研究工作区维护，不是运行依赖，也不随公开代码仓库发布。下列标识、原路径和哈希用于追踪，旧包名不作为当前方向或平台模块名称。

## 需求建模方向的既有原型

来源资产标识：`prime-code-audit-2026-09-21`。审计条目为 `source-review-snapshot.zip` 与 `source-inventory.json`；资产名称保留历史身份，不表示本仓库包含该 ZIP。

| 原条目 | SHA-256 | 采用范围及行为改变 |
|---|---|---|
| `src/prime_mde/model.py` | `4ec1f97226875931402235d6d4743fcae846fb1fc19f70acfdf8edeec598ea8f` | 引用机制重实现；来源类别、确认与适用性分开 |
| `src/prime_mde/operations.py` | `37ce02e0be6bdb15f07f84d6ac536dda6e727877a3571f0548dd04cfe5f99b52` | 有限类型化操作重实现；未知字段拒绝、标量元模型不固定领域 |
| `src/prime_mde/kernel.py` | `3223978b78f84a73b23af9886bd23afc3c848f8a5c1d9c774d64da417d3dbddb` | 预览/提交分离；绑定决定、去掉全状态回调、单实例内存锁 |
| `src/prime_mde/impact.py` | `8a161eaf5517aa25a29bf5fbe55615f46321933b2ab5c09b7ebb1d910c29eb95` | 前后依赖闭包重实现；包含关系分离、报告不可变、适用性另算 |

相关目标是 protocols/model-kernel。来源审计中的原样测试为 31/32 通过，仍有差异漏检、过度失效及形式化/指标边界；不能将原型测试或来源机制存在当作本平台正确性的证据。文件仓储、UI、形式化导出、指标与完整需求差异方法均未整包采用。

## P0 历史来源

来源资产标识：`p0-code-2026-09-20`。条目 `src/validation/v2/repair_loop.py`，SHA-256 为 `a542127d6570dbe184785ee7ee6acfd222c2db223cc1c081e3a46137b3a5eb2a`。其纯报告比较机制适配至 generation 的 `compare_reports`。

保留“不新增诊断、已评估覆盖不回退、严格改善”原则；改为绑定同一检查上下文、义务集合和版本，不继承覆盖豁免。修复改善不授予模型提交或应用交付许可。未采用 XML/AUTOSAR 身份、完整修复循环或原领域流水线。

该来源是当时开发树选取的源码快照，不冒称论文冻结提交。P0 历史结果不构成新平台结果；当前只有报告级正反例，不能据此宣称原领域端到端回归完成。

## 版本与许可

本仓库代码版本由 Git 提交保存；当前工作树不存放重复往期代码目录或 ZIP。首轮离线切片的 58 个原始输入文件保存在[历史提交 19f67dce](https://github.com/Abandooon/ModelSpine/tree/19f67dce04c1fbd468a2ca4ea3dee7eb18fee30f)，标签为 `archive/offline-slice-2026-09-21`；该归档与当前 main 分开，历史文档保留当时的路径和设计语境。

原始采集 ZIP 位于该提交的 [historical-evidence/source-snapshot.zip](https://github.com/Abandooon/ModelSpine/blob/19f67dce04c1fbd468a2ca4ea3dee7eb18fee30f/historical-evidence/source-snapshot.zip)，大小 58,999 字节，SHA-256 为 `3a923e290ec91c753e21ac204009fc8ccb120572edbdc7e00d9e7273857c4c3c`。2026-09-22 经授权发布并从远端读回核验后，研究工作区已删除重复 ZIP，按完整 Git 提交读取原字节进行完整性检查。原运行日志与清单仍保管于研究工作区；迁移不改写测试结果，也不表示原运行时已存在 Git 提交。来源哈希用于核对原条目，Git 提交用于定位本仓库实现，两者不能相互替代。

已登记来源许可为：P0 来源项目 Apache-2.0；需求建模方向既有原型 MIT。实际适配记录按上述条目与哈希保留。平台整体当前未声明项目许可证；来源许可不自动为所有新增代码赋予同一许可。本文不授予额外授权，也不推定整个旧框架均已纳入平台。
