# language/0.2-draft：可复核载荷与组合

以下均为公开、人工构造的设计/工程样例，不来自B独立原文或期待，不用于证明自然语言能力。载荷是language-0.2的具名片段：`L(x)={element:x}`，`R(p,v,h,x)={package:p,version:v,hash:h,element:x}`，`K(x)=Known(x)`，`U(reason)=Unknown{reason,evidence:[]}`；展开宏后字段含义按语言合同。hash用`H(实际包规范JSON)`计算，不能把本文的H表达式当成有效SHA256输入。正/反/未知分别指相应层次，语法非法不是业务false。

## 各轴载荷

|轴/固定声明|正例载荷→结果|反例载荷→结果|未知载荷→结果|
|---|---|---|---|
|数值/单位：`Quantity{number:Decimal{precision:6,scale:2,rounding:reject},dimension:"mass",unit:"kg"}`，`kg.scale=1,g.scale=1/1000`|`K({number:"1.25",unit:"kg"})`显式convert g→1250.00|`K({number:"1.251",unit:"kg"})`精度拒绝；`unit:"second"`维度类型错误|`U("unit not specified")`→unknown；不可猜kg|
|时间：`Instant{resolution:"second"}`，截止`2026-01-01T00:00:00Z`|`2026-01-01T08:00:00+08:00`归一后与截止相等|`2026-02-30T00:00:00Z`非法日期；无时区不进入Known|`U("source says tomorrow; timezone missing")`→unknown|
|枚举/记录/联合/集合：`Enum members=[red,blue]`；`Union variants=[{tag:count,type:Int[0,9]},{tag:color,type:Enum}]`；集合0..2 ordered=false unique=true|`K([{tag:"count",value:2},{tag:"color",value:"red"}])`合法|`K([{tag:"color",value:"green"}])`不属于枚举；`[2,2]`在unique集合拒绝|`U("variant not selected")`→unknown；`K([])`已知空集合|
|缺失/空：`Field amount required=true nullable=true`|`slots:[{field:"amount",state:"null",value:null}]`结构满足|`slots:[]`required违反|`slots:[{field:"amount",state:"unknown",value:null}]`未知，不能当Null|
|继承/派生：`Special bases=[Base]`，Base.size Int[0,9]，derived total=`size+1`|`Special{size:2}`→total3且满足Base约束|`Special bases=[Special]`循环拒绝；`size derived=total,total derived=size`循环拒绝|`Special{size:U("unanswered")}`→total unknown|
|多元/包含：`Allocation roles=[worker,tool,shift]`，tool bounds1..1固定worker/shift，字段hours；composition owner=assembly|`(w1,t1,s1,hours=2)`加上所有声明worker/shift组合满足下界|同一`(w1,s1)`有t1和t2→违反；同一part有两个assembly→违反|工具包未装载/人口闭包不完整→unknown，不拆成二元通过|
|规则组合：`applies=active,assertion=(count>=2 AND licensed),unless=exempt`|active=true,count2,licensed=true,exempt=false→satisfied|active=true,count2,licensed=false,exempt=false→violated|active=U,exempt=false→unknown；active=false→not_applicable；nullable count参与比较→error|
|状态/操作/并发：`draft --submit[complete]--> submitted`，version_compare|`state=draft,version=4,expected=4,complete=true`→新version5/submitted|expected3→conflict；complete=false→拒绝不产生新状态|complete=U→indeterminate；无运行回执→not_run|
|过程：`Start→Fork(A,B)→Join(all)→End`，A/B写集互斥|A done、B done、同fork实例→End|A/B写相同字段且无隔离声明→定义拒绝|A done、B pending→pending；deadline后→timeout|
|权限/外部：deny_overrides；允许operator且状态ready；API返回温度|operator/ready、无deny，匹配API回执`request=q1,value=20`→permit与Known20|true deny即deny；回执request=q2与q1错绑→conflict|角色成员关系U→indeterminate；设备失联→unknown，超时回执→timeout|
|质量/媒体：`metric=p95_latency,unit=ms,workload=100rps,samples=100,threshold=200,method=nearest_rank`|100样本第95排序值180→satisfied|100样本第95值220→violated；把失败请求删分母→报告拒绝|只有90样本→unknown；Resource哈希正确但未评音质→not_run|
|视图/代码：`View mode=review,bindings=[widget:limit→rule:cap]`，cap=2|展示“至多2”；编辑绑定候选v1→v2检查|业务代码实现cap=3→violated；修改layout同时修改cap→非法动作|代码没有trace→unknown；未构建→not_run|
|演化/维护：cap从3改2，既有对象count3，file owner=human/hash=h1|count2模型、文件仍h1且计划不覆盖人工文件→可预览迁移|count3旧数据→violated；文件hash=h2却expected h1→conflict|追踪覆盖未知→unknown；没有恢复器→recovery not_available|
|忠实与共同错误：公开原文“至少两个”|候选`count>=2`，实例count2→内部满足且符合本公开断言|候选/检查器都用`count<=2`，count1内部通过，但独立原文判断失败|“若可行尽量两个”模态未澄清→unknown，不能确认硬下界|

## 四组组合的求值推演

### 数量 × 时间

声明：`events:Collection<Event>`，Event.timestamp:Instant；窗口`[now−Duration(86400s),now)`，`now`作为绑定输入，禁止取求值机当前时间；规则Count(Filter(events,e.timestamp≥start AND e.timestamp<now))≤2。原始集合必须有闭包/观测范围。

```json
{"now":"2026-01-02T00:00:00Z","complete":true,"events":[
 {"id":"a","timestamp":"2026-01-01T00:00:00Z"},
 {"id":"b","timestamp":"2026-01-01T23:59:59Z"},
 {"id":"c","timestamp":"2026-01-02T00:00:00Z"}]}
```

正：a/b计入、c右边界排除，count2满足。反：再加`d@2026-01-01T12:00:00Z`→count3违反。未知：将b.timestamp改Unknown或complete=false→Filter/Count未知。无时区timestamp是输入未决；不能截日期代替窗口。本轮finite count无Filter/Instant，必须整体残余，不能只计全历史后报支持。C若支持结构但不支持时间，Support应列时间规则residual、不可全义务采用。

### 权限 × 状态

Policy allow=`role=operator AND state=ready`、deny=`suspended=true`，动作run要求expected_version。状态机ready→running，更新与授权检查属于同一version_compare事务。

```json
{"actor":{"role":"operator","suspended":false},"object":{"state":"ready","version":7},"command":{"action":"run","expected_version":7}}
```

正：permit且转running/v8。反：state=running→没有true allow，deny；或suspended=true→deny；检查后另事务改为v8，旧命令→conflict，不能沿用v7许可。未知：suspended=Unknown→indeterminate，状态不变。Web服务和桌面应用服务均消费同一policy/state refs；按钮可见不是permit。本轮只可将ready/role作为工程标量输入求纯Bool，不能因此宣称授权/迁移执行器可用。

### 继承 × 基数

BaseCrew.members:Person集合0..5，SpecialCrew继承收窄2..3；effective bounds=max(min)=2、min(max)=3，继承全部规则。Person不因角色被复制。

```json
{"type":"SpecialCrew","members":["p1","p2"],"complete":true}
```

正：2满足两个层次。反：members=[p1]→特化下界违反；SpecialCrew把最大改6→弱化父界，定义拒绝；父界0..1与特化2..3→空交集，定义不一致。未知：成员闭包=false→unknown；没有显示成员不代表0。多继承两个来源同名不同字段ID须rename，不悄悄覆盖。本轮不自动flatten继承；C的来源支持如果仅单继承必须显式拒绝冲突多继承，回传对应残余。

### 跨包 × 版本

包A@1引用`R("B","1",H(B1),"Person")`；B1.Person.status枚举{active,inactive}。B2.Person.status新增pending。A成员关系指向B1.Person，参与对象绑定B1模型。

```text
正：imports=[ArtifactRef(B,1,H(B1))]，对象type=B@1/Person且status=active。
反：提供B@2内容却声称B@1/H(B1)→conflict；以B2/pending对象参与A的B1角色→类型/版本拒绝。
未知：缺B1包原字节→unknown closure，不尝试从网络取latest。
迁移：A2显式改引用B2/H(B2)，列旧报告stale、枚举穷尽性回归及对象迁移；保留A1/B1。
```

包循环引用不等于继承循环；本草案对跨包内容哈希依赖要求DAG，A引用B且B引用A即拒绝，即使没有继承环也不能用两阶段解析声称哈希可构造。可计算的A→B双包载荷及循环反例见language-0.2身份节。单包内A.X继承B.Y且B.Y继承A.X也独立违反继承DAG。本轮finite profile本包引用封闭，跨包不得抹除限定身份压成局部字符串。

## R1和旧标量的映射/拒绝

R1 Concept{id:c,name:N}→Entity{id:c,name:N,abstract:false,bases:[],renames:[],fields:[],identity:[]}，但这只是概念声明，不伪造实例。R1 Attribute{id:a,concept_id:c,value_type:integer}→类型Int64；其required/nullable/多重性/身份未提供，保留未决字段，**不得填required=true/nullable=false**。因此含属性的R1不能自动直接进入finite-domain，须新来源/回答补足。R1未知value_type保持Unknown+issue。R1 Relation双向已知基数→二元association两角色，target角色取targets_per_source，source角色取sources_per_target；任一null基数拒绝可执行投影并保留问题。R1 Rule.text/not_formalized→原文义务Residual(required按来源模态)，不推导恒true Constraint。例：规则“24小时内最多2个”不能映射为全历史关系max2；反向从时间规则导出R1只能带原文规则+显式有损报告，不可报exact。

旧Metamodel KindSpec(name=Device,FieldSpec(name=enabled,type=boolean))→实体ID Device、字段ID按`Device.enabled`分配、required=true、nullable=false、单值Bool；这两个限定来自旧内核的实际语义，有理由而非猜测。旧字段name是结构键，名称变化须映射ID并保留追踪。反例：旧Element.parent/dependencies仅保留开发包含/依赖元数据，没有来源证明时不能转领域owns/precedes关系。旧标量字符串中编码日期、JSON、图边不自动获得日期/关系语义。

finite→旧内核实际API `modelspine_kernel.domain_projection.to_scalar_metamodel`仅支持：至少一个实体、全部字段required/nonnullable、无关系/约束/残余。以entity/field稳定ID作为kind/field键；display name留在原定义，由引用保留，不是领域键。`enabled:boolean`正例可映射；`enabled nullable=true`、任何binary relation、cap表达式或Residual均返回unsupported，**不返回部分Metamodel**。该API只导出定义，不迁移实例、不接受候选、不提交模型；旧快照还有category/source/dependencies等独立前提。
