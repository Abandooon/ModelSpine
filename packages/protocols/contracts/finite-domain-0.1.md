# finite-domain/0.1：当前构造/检查出口

状态：2026-09-28实现的实验配置，待总领审核；完整设计见[language/0.2](language-0.2.md)。唯一运行类型定义是`modelspine_protocols.domain_language`的dataclass；共享严格decode/dumps拒绝未知字段、重复键、浮点、bool冒充int。所有dataclass字段必填，空数组显式提供。下面的例子与源码是C一次试验的输入边界，不能把本配置称为完整元元模型。

```json
{"schema_version":"finite-domain/0.1","id":"sample","version":"1",
 "entities":[{"id":"item","name":"Item","fields":[
   {"id":"enabled","name":"Enabled","value_type":"boolean","required":true,"nullable":false}]}],
 "relations":[],"constraints":[{"id":"enabled-rule","context":"item",
   "applies":{"op":"literal","args":[],"symbol":null,"value":true},
   "assertion":{"op":"field","args":[],"symbol":"enabled","value":null},
   "unless":{"op":"literal","args":[],"symbol":null,"value":false}}],"residuals":[]}
```

DomainDefinition有schema_version/id/version/entities/relations/constraints/residuals。全局本包ID唯一、非空、无冒号；最大256项（包含field）；本地ID是字段/关系引用键，名称仅显示。entities是EntityType(id,name,fields)，每字段仅string/integer/boolean和required/nullable。整数为有符号64位。relation是BinaryRelation(id,name,source,target,targets_per_source,sources_per_target)，bounds minimum≥0，maximum整数≥minimum或unbounded。它是无属性、无顺序、无包含含义的distinct二元tuple集合。无继承、跨包、集合属性或隐式单位。

Constraint(id,context,applies,assertion,unless)逐实例求值；三个表达式均Bool。Expression(op,args,symbol,value)恰这四字段，op的语法/类型：

|op|args/symbol/value|类型和求值|
|---|---|---|
|literal|[]/null/标量|相应已知类型，不能用null字面量冒充Bool|
|field|[]/当前context字段ID/null|字段类型；slot未提供的结构事实在读取边界转为unknown，显式未知→unknown，业务null保留|
|count|[]/`relation_id:out`或`:in`/null|Int；只计该对象相应方向全部distinct边，人口闭包不完整→unknown|
|eq / lt / le|2子式/null/null|操作数同类型；排序仅Int；任一侧Null参与→error，即使另一侧unknown或读取缺失字段；不隐式转false|
|and / or / implies|2子式/null/null|非nullable Bool；强Kleene，error优先|
|not|1子式/null/null|非nullable Bool；unknown传播|
|is_null|1子式/null/null|已知值false、Null true、missing/unknown为unknown|

树深≤24、每个predicate≤512节点；没有循环、Python eval、插件代码或网络。有限执行含义与完整语言对应算子一致。本配置没有Get/Filter/量词/算术/时间执行；条件计数必须保留完整残余，不能通过count改成无条件规则。Residual(id,family,text,required)保存未执行语义与来源，所有残余都逐项返回unknown，必需残余阻止完整支持/交付；完整族的设计含义仍由language-0.2定义。

ProjectModel(schema_version=finite-project/0.1,id,version,definition:ArtifactRef,objects,links,population_complete)。定义ref的project_id由调用方指定，artifact_id/version/hash必须对应实际DomainDefinition。Instance(id,entity,slots)，Slot(field,state=known|null|unknown,value)，null/unknown的value必须null；Missing由slot不存在表达。Link(relation,source,target)。实例ID唯一，字段不重复/越界，端点类型符合；最多256对象/4096边，重复边拒绝。population_complete是调用方的事实声明，不由检查器证明；false时聚合unknown但观察到超上界仍可证伪。

`apps/domain_checks.py:check_project(definition,project,project_id=...)`纯本地检查，不写状态；报告绑定definition_hash、project_hash、checker=`finite-domain-checker/0.1`和完整逐项结果。缺字段required→violated；类型错误→violated且相关规则error；可选缺失→not_applicable、读取它→unknown；已知0/false/空串保留。没有context实例为not_applicable（封闭）或unknown（开放），不是非空语义见证。语言良构不证明实例可满足性或原文忠实，后者固定not_checked。

构造入口`typed-domain-candidate/0.1`由requirements持有：request_hash、status=unconfirmed、definition、traces、issues。Trace(element,evidence)恰覆盖每个定义ID一次，沿用R1原文行引文；issues沿用ModelingIssue字段但不进入定义语义。解码和类型检查通过只得到references_and_types_checked；缺来源/错请求/错误引用/非法类型直接失败，不产生部分有效候选。该入口可以检查人工候选，不能认证生成来源。

CLI：原有prepare/prompt/inspect保持R1语义；新增typed-prompt、typed-inspect、check-project（后两者带--request/--response，check-project另带--project-model）。退出0表示报告完成，仍可能violated/unknown/error/not_applicable；退出2为输入/绑定/文件错误。输出文件不覆盖。构造prompt只读宿主固定的原文请求及通用语言指令，不读取任何expectations或heldout。

支持：单包实体、三标量、可选/可空字段、二元关联双向基数、有限条件Bool与count、部分信息、来源/版本/实例报告。拒绝：未知字段/operator/引用、错绑定、跨包与继承的直接载荷、把时间/权限/复杂行为伪作已执行。保留：以明确Residual承载配置外原文义务，报告不改成通过。未做：LLM传输、语义忠实验收、提交、业务授权、应用生成。
