# finite-domain/0.2：有限集合、整秒时间与资格检查

本版本对应 [language-0.2](language-0.2.md) 的 Get/Navigate/Filter/Count、强 Kleene 逻辑及 Instant/Duration 有限子集。语义所有者为 protocols；执行装配在 `apps/domain_checks.py`。旧 [finite-domain/0.1](finite-domain-0.1.md) 的 DTO、算子和求值不修改；没有把旧 count 改成带过滤的 count。严格类型见 [finite_execution.py](../src/modelspine_protocols/finite_execution.py)。

封闭 Definition 字段仍是 `schema_version,id,version,entities,relations,constraints,residuals`，版本常量为 `finite-domain/0.2`。Entity/Field/Relation/Bounds/Residual 形状同旧版，Field.value_type 增加 `instant`。ProjectModel 仍用 `finite-project/0.1`，definition 引用必须绑定新定义准确 project/id/version/hash，不能只改版本文本后重用旧报告。每条已知时间是 `YYYY-MM-DDTHH:MM:SSZ`，Gregorian 年 0001–9999、UTC 整秒；拒绝偏移、亚秒、闰秒、无效日期、bool/数字时间。缺失、业务 null、认识 unknown 仍分别处理，无默认值。

Constraint 新增必需字段 `scope,operation`：`invariant` 要求 operation=null；`eligibility` 要求非空 operation 标签。标签是只读前置资格查询，不是已经实现的全局 Operation/Policy 或业务状态机。`check_project` 只检查结构与 invariant；`check_eligibility(definition,project,project_id=...,operation=...,target=...)` 加查指定实例的同标签 eligibility，未知标签/目标拒绝，不退成全库检查。后者返回 `{scope,operation,target,report,action_execution:"not_run"}`；report 包含结构、不变量、指定资格与所有 residual 结果。满足资格断言不等于提交、持久化修改、历史保留或权限批准。作用域映射到全局 Rule invariant / Operation precondition；尚无动作后置效果执行。

因此合法存储的 0/1 条历史记录可以在资格检查中失败，不能为强制计数把它们设成全库非法。存储关系基数与过滤计数分别声明；执行器不预定业务名称、必需/空值、正反向基数或任何上下限。关系是不同对象对的集合，重复边拒绝，Navigate 返回不同目标对象；其他父对象下的成员不进入本次遍历。

所有 Expression 恰有 `{op,args,symbol,value}`：

| op | args | symbol | value / 静态结果 |
|---|---|---|---|
| literal | [] | null | integer/string/boolean 值 |
| instant / duration | [] | null | 时间字符串 / signed64 整秒；Instant / Duration |
| self | [] | null | null；固定当前规则上下文对象 |
| var | [] | 词法变量名 | null；绑定的对象 |
| get | [object] | 对象类型中的 field ID | null；声明的标量类型及 nullable |
| navigate | [object] | relationID:out 或 :in | null；目标对象集合 |
| filter | [collection,predicate] | 新成员变量名 | null；同类型集合，禁止变量遮蔽 |
| count | [collection] | null | null；Int |
| eq/lt/le | [left,right] | null | null；Bool，同标量类型，lt/le 仅 Int/Instant/Duration |
| and/or/implies | [left,right] | null | null；非空 Bool 输入及结果 |
| not/is_null | [arg] | null | null；Bool |
| add/sub | [left,right] | null | null；Int±Int、Duration±Duration、Instant±Duration；Instant−Instant→Duration |

不允许 Instant+Instant、bool 冒 Int、隐式时间解析或隐式单位转换。整数为 signed64，算术溢出和跨出日期范围产生 error。没有浮点时间、任意字符串脚本、隐式笛卡尔积或循环。

普通比较/算术读到 Null 是 error，不能被 Unknown 遮盖；IsNull 是显式例外。Missing 读为 unknown，required 缺失的结构义务另为 violated；optional 缺失的结构义务为 not_applicable。非法实例字段导致相关对象访问 error。所有已求值 error 优先于逻辑吸收律；其后采用 false AND unknown=false、true OR unknown=true。已知空集合计数 0。开放 population 的聚合 unknown，不用已观察数量冒充闭包。

**保守 Filter 不提供精确区间计数。** 任一成员谓词 unknown→整个集合 unknown→Count unknown；确定窗外或不合格 AND unknown 可为 false，error 仍优先。2 个确定合格 + 1 个可能计入为 unknown；5 个确定合格 + 1 个可能计入也为 unknown。它们不是精确业务允许/拒绝结果。若来源要求“未知不可能影响结果时必须给出确定充分必要判定”，此精度义务仍须 required residual，不能用本算子声称全部满足；本版本不增加另一个区间算子。历史保留同样仍为未执行 residual，纯 checker 不删数据不证明生命周期义务。

资源上限：256 定义元素/实例、4096 唯一边、表达式深度 24、每谓词 512 节点；超限 `unsupported`，不是业务最大值，不截断数据。重复/悬空/错类型边、错引用和非法 AST 拒绝。旧 v1 检查器和旧 LocalWeb 消费者不能把 v2 载荷按 v1 解码；ApplicationSpec v0.1 将其明确阻塞为 `unsupported_definition_profile`。

工程可调用例见 `tests/test_finite_execution.py` 的文档批次/审计事件夹具（hand_authored_engineering_only）；它覆盖资格与存储分离，不是自然语言抽取结果或独立语义验收。
