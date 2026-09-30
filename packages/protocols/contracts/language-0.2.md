# ModelSpine language/0.2-draft

2026-09-28。完整语言设计的规范性草案，供人工逐条复核及后续编译器实现；不是全部已实现的交换解码器。当前运行配置为[finite-domain/0.1](finite-domain-0.1.md)，其严格载荷不接受本页全部构造。新业务词汇由来源发现，本规范不包含业务术语答案。有限配置外的设计不能用一个`unsupported`替代；以下分别给出结构、良构与解释。

## 身份、记法和唯一语义所有者

下列记录是封闭积类型：列出的字段全部必填，无隐式默认值；`T?`是显式JSON null或T，`[T]`是数组，`A|B`由tag区分，ID为非空UTF-8字符串。同一Package内所有声明ID唯一。`Ref={package,version,hash,element}`，hash为被引用包规范JSON字节的SHA256；本包引用为`Local={element}`，由包身份限定。统一元素引用为`ElementRef=Ref|Local`：这是按封闭键集合区分的引用和式（仅此和式不加tag）；Local恰有element，Ref恰有package/version/hash/element，混合/缺键非法。本文所有field_ref/type_ref/operation_ref/role_ref等元素引用及数组元素均为ElementRef，另标ArtifactRef/EvidenceRef的制品引用不受此别名替换。引用可显示名称，但不按名称解析。外包采用精确版本闭包，不访问网络、不解析latest；同包同版本不同hash为conflict。本草案仅支持哈希依赖为DAG的包闭包，跨包引用环（包括无继承环的普通引用）明确拒绝为unsupported/cyclic_package_hash_dependency。继承/派生/包含等自己的环规则另行检查。ArtifactRef沿用protocols已实现定义；不得将内容哈希省略成路径。

`Package={id,version,language,imports:[ArtifactRef],profiles:[ArtifactRef],declarations:[Declaration],traces:[Trace]}`。`language`钉住本规范版本及分发文件hash；规范发布时固定，草案改字节须换hash。`Trace={element:Local,requirements:[ArtifactRef],evidence:[EvidenceRef],category:intent|fact|hypothesis,confirmation:unconfirmed|confirmed|rejected}`。事实来源和用户确认正交。语言定义不承诺用户需求穷尽。

`language`为ArtifactRef，必须是包闭包之外已固定的语言制品；不得把某个包自己的生成/审计清单反向嵌回包字节。每条外部Ref必须对应imports中同id/version/hash的制品；imports包含相应制品的宿主project_id，闭包内Package.id唯一（同id同时导入不同版本须拒绝，迁移显式选择）。所有参与规范字节的外部依赖，包括profiles/trace制品，均不得反向依赖当前包内容哈希；追踪生成代码/运行结果的反向关联放在独立后继Trace/Evolution制品，不纳入旧包字节。自包引用必须用Local，禁止自hash引用。DAG先从叶子算规范字节/hash，再写父包imports及Ref；装载拓扑排序用于解析，不是求哈希固定点。

两包身份载荷（下面是可直接执行的Python构造；L是宿主已固定、实际可解析的语言ArtifactRef参数。函数不猜L、不访问网络；返回的A/B均为完整Package记录）：

```python
import hashlib, json
def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()
def two_packages(L):
    B = {"id":"B","version":"1","language":L,"imports":[],"profiles":[],
         "declarations":[{"kind":"data_type","body":{"id":"flag","name":"Flag","type":{"tag":"Bool"}}}],"traces":[]}
    hb = canonical_hash(B)
    A = {"id":"A","version":"1","language":L,
         "imports":[{"project_id":"demo","artifact_id":"B","revision":"1","content_hash":hb}],"profiles":[],
         "declarations":[{"kind":"data_type","body":{"id":"enabled","name":"Enabled",
             "type":{"tag":"Named","ref":{"package":"B","version":"1","hash":hb,"element":"flag"}}}}],"traces":[]}
    return {"A":A,"B":B,"hash_A":canonical_hash(A),"hash_B":hb}
```

正：B.imports=[]，A.imports=[B@1/H(B)]，A.enabled.type.ref.hash同为H(B)，两者哈希可以顺序计算，无回填。反：在此B中加入`imports=[{project_id:"demo",artifact_id:"A",revision:"1",content_hash:旧H(A)}]`及指向A的Named ref，图变A→B→A，立即拒绝；重新计算B再替换A中的H(B)仍不能解除环，禁止反复回填到“看似稳定”。未知：缺L或B原字节只可保留closure unknown，不可用零hash/最新包替代。本轮不实现新装载器；互相引用的领域类型可在同一包用Local表达，跨包SCC身份方案若未来需要须独立修订合同，当前不承诺支持。

本文Type/Expr/Effect等和式的线格式为`{tag:"构造名",...该构造列出的字段}`，不能额外夹带任意JSON。声明统一为`Declaration={kind,body}`，kind/body配对为data_type/`{id,name,type:Type}`、entity/Entity、value_object/ValueObject、relation/Relation、constraint/Constraint、operation/Operation、state_machine/StateMachine、process/Process、policy/Policy、external/ExternalContract、quality/Quality、task/Task、view/View、evolution/Evolution。body.id进入包统一ID空间；内嵌字段/角色/迁移ID在包内也唯一；Ref.element是稳定ID，不拼接显示名称或位置路径。finite profile不直接接受此完整格式。声明未按其kind匹配形状即语言非法，而非执行不支持。

|唯一所有者|拥有的语义/数据|其他消费者职责|
|---|---|---|
|protocols语言合同|值、类型、表达式、引用、构造组合的含义与交换格式|其他模块引用此定义，不另造第二种Count或Null|
|requirements|来源、需求模态/解释、问题回答、候选和确认记录|引文正确不自动证明忠实|
|model-kernel|已接受设计状态、版本、影响、保存及迁移提交|不持有业务运行数据；有限投影不能升级表达能力|
|assurance|义务、ValidatorSpec、执行计划、支持/结果解释|检查器实现语义配置；不能改业务声明以使其通过|
|显式执行适配器|一个已钉住profile的实际求值|本轮`apps/domain_checks.py`只实现finite-domain/0.1；不自定义领域词汇|
|interaction|任务/布局/呈现与版本绑定的审阅动作|引用同一规则，不拥有另一套规则真值|
|generation|生成单元、构造约束与修复轨迹|不得改语义基准、公开验收或保留评价答案|
|implementation|目标映射、命令实现、事务/并发、文件/构建/迁移执行|服务端/本地服务最终执行业务权限|
|component-reuse / code-intelligence|分别拥有来源能力观察 / 代码事实追踪|无权把来源声明/实现现状替换用户意图|

## 值与类型

`Cell(T)=Known(T)|Null|Unknown{reason,evidence}|Missing`。Missing是输入未提供，不是可序列化业务值；序列化时省略slot且由字段required判断。已知空集合不同于Missing。Error只出现在求值结果，不可作为有效业务值。

`Type=Bool|Int{min,max}|Decimal{precision,scale,rounding}|String{min_length,max_length}|Enum{members:[{id,label}]}|Record{fields:[Field]}|Union{variants:[{tag,type}]}|Collection{item,min,max,ordered,unique}|Date|Instant{resolution}|Duration{resolution}|Quantity{number,dimension,unit}|Resource{media_type,locator_scheme,integrity_required}|Named{ref:Ref|Local}`。

良构：Int界在有符号64位内且有序；Decimal用十进制字符串，precision>0、0≤scale≤precision，rounding=reject|half_even，不接受浮点自动转换；String长度按Unicode码点，界有序；Enum成员ID唯一且非空；Record字段ID/名称各唯一；Union tag唯一、输入恰有一tag；集合max为非负整数或unbounded，unique按规范值相等，ordered=false时哈希按规范值排序，仍拒绝重复而非自动去重。Named只引用数据类型或实体类型；结构递归必须通过引用/集合，禁止无限按值展开。

Date为有效公历YYYY-MM-DD；Instant输入必须有UTC偏移并规范为UTC整数tick，resolution明确tick大小，保留原时区呈现元数据。无偏移时间为Unknown待澄清，不能取本机时区。Duration为整数tick，不把月换算固定秒。Quantity是精确数及单位ID；单位表`Unit={id,dimension,scale:{numerator,denominator},offset}`，分母非零，换算`canonical=value*scale+offset`，不同维度不比较；仅同维度显式convert可换单位，溢出/精度丢失按rounding拒绝或记录。Resource值为`{locator,media_type,hash}`，检查引用完整性不证明媒体质量或资源可访问。

## 结构、关系与组合

`Entity={id,name,abstract,bases:[ElementRef],renames:[{field_ref:ElementRef,name}],refinements:[FieldRefinement],fields:[Field],identity:[ElementRef]}`；`ValueObject`同记录但无独立对象身份、bases/renames/refinements/identity均为空。`Field={id,name,type,required,nullable,multiplicity:{min,max,ordered,unique},default:Expr?,derived:Expr?}`。required要求slot存在；nullable允许Null；multiplicity控制slot中的成员数，不能用0..1代替可空。default/derived不得同时存在；默认值有来源和显式materialize记录，不能写成原文承诺。派生值只读、纯、类型兼容，依赖图无环。identity字段必须required/nonnullable、不可变且可判等，按实体有效类型作用域唯一。

继承为多重特化DAG。类型闭包按祖先集合合并；同源祖先同ID只继承一次。不同字段ID重名必须显式rename映射，不能按遍历顺序选一项。细化只通过`FieldRefinement={field_ref:ElementRef,type:Type,required:Bool,nullable:Bool,multiplicity:{min,max,ordered,unique}}`表达；它引用已有字段而不是新声明，不含id/name/default/derived，不进入声明ID集合。Entity.fields仅声明新字段，不能重复父字段ID或用新ID冒称覆盖。细化须保留field_ref限定身份、类型协变、不得增加nullable或弱化required，集合区间只能收窄；对可写字段类型必须不变，操作参数逆变/返回协变。继承约束全部合取，不能覆盖删除。冲突区间、无可实现枚举/类型交集为定义不一致，不用“没有实例”掩盖。

refinements属于派生Entity，每个field_ref最多一条且必须解析为继承闭包内的字段；指向自有/非字段元素非法。对所有继承路径的同一身份先合并有效限制，再检查本地细化相对每条路径都不弱化；互斥界/类型无共同实现即invalid。ordered不得改变，unique=true不得改false；default/derived从原声明继承，不允许用细化替换或删除，若继承默认/派生不满足新类型或界则本草案拒绝该细化，不能静默改值。可写字段（derived=null）类型保持不变，只读派生字段可协变；required/nullable与界的规则对二者相同。名字变化单独由renames表达，实例slot/Get始终引用最初声明的field_ref。protocols唯一拥有这些定义语义，其他消费者不能另行flatten后改变身份。

renames属于派生Entity，不属于父Field或消费UI。每条field_ref必须是该实体继承闭包内一个字段的完整限定身份；相同field_ref最多一条，name非空。只改变该实体有效字段的本地可见名称，不创建新字段ID、不更改父定义、类型、约束或实例slot引用。先按身份合并祖先字段，应用本实体renames，再核对有效字段名（含自有字段）唯一。菱形继承中同一字段经两路径得到不同有效名称时，本实体必须显式指定该field_ref的新名称；不得依遍历顺序选名。无法解析父包→unknown；映射到非继承字段、重复映射、仍有同名→invalid。

具体同名冲突载荷（Field完整展开；包内引用用Local）：

```json
[
 {"id":"Left","name":"Left","abstract":false,"bases":[],"renames":[],"refinements":[],"fields":[{"id":"left_code","name":"code","type":{"tag":"Bool"},"required":true,"nullable":false,"multiplicity":{"min":1,"max":1,"ordered":false,"unique":true},"default":null,"derived":null}],"identity":[]},
 {"id":"Right","name":"Right","abstract":false,"bases":[],"renames":[],"refinements":[],"fields":[{"id":"right_code","name":"code","type":{"tag":"Bool"},"required":true,"nullable":false,"multiplicity":{"min":1,"max":1,"ordered":false,"unique":true},"default":null,"derived":null}],"identity":[]},
 {"id":"Combined","name":"Combined","abstract":false,"bases":[{"element":"Left"},{"element":"Right"}],"renames":[{"field_ref":{"element":"left_code"},"name":"leftCode"},{"field_ref":{"element":"right_code"},"name":"rightCode"}],"refinements":[],"fields":[],"identity":[]}
]
```

正：Combined有效字段为left_code→leftCode、right_code→rightCode，父定义中的两个code不变；规则仍按原字段ID访问。反：Combined.renames=[]会保留两个不同ID的code，拒绝；把第二条name改leftCode也拒绝；把field_ref改Combined（不是字段）拒绝。未知：Right外包缺失时无法确认完整有效字段集合，不能用只加载Left的结果宣称无冲突。这里只补设计载荷，finite-domain/0.1仍不接受bases/renames/refinements。

`Relation={id,roles:[{id,type:Ref|Local,bounds:{min,max}}],fields:[Field],semantics:association|composition,owner_role:role_id?,opposite_views:[{id,from_role,to_role}]}`。roles≥2且ID唯一。实例`RelationObject={id,relation_ref,participants:{role_id:object_ref},slots:[Slot]}`恰有每个角色一次；多值参与必须拆成多个显式元组。每个角色bounds表示固定其余角色元组后，该角色不同对象的数量；另需对所有合类型其余元组（包括零连接）检查下界。只对已观察到的连接计下界是不完整验证。关系字段属于整个元组，n元不得拆边丢失联合语义。重复参与元组如有多个关系对象，计数按distinct对象；重复事件须用明确事件实体表达。二元无属性关系可紧凑存储为去重边集合。

composition恰有owner_role，其余角色是被拥有对象；一个对象跨全部组合关系至多一个owner，owner→part图无环；删除owner默认拒绝存在part的操作，只有Operation显式cascade及其义务才可级联。association没有包含/删除语义。opposite是同一事实的投影视图，不能存两份各自可写的真值。跨模型参与者也必须绑定模型版本/hash；缺闭包返回unknown，不当成悬空对象已不存在。

## 表达式、类型与求值

完整设计的表达式AST由tag和字段决定，禁止执行字符串：

```text
Lit{type,value} | Var{name} | Get{object,field_ref} | Navigate{object,relation_ref,from_role,to_role}
Compare{operator:eq|lt|le,left,right} | Arithmetic{operator:add|sub|mul|div,left,right}
Logic{operator:and|or|implies,left,right} | Not{arg} | If{condition,then,else}
ForAll{collection,var,predicate} | Exists{collection,var,predicate}
Filter{collection,var,predicate} | Count{collection} | Sum{collection}
IsNull{arg} | IsMissing{arg} | Convert{arg,unit_ref}
ExternalObservation{contract_ref,observation_ref,arguments:[Expr]}
```

变量词法作用域、禁止未绑定变量；Get按静态类型查有效字段；Navigate返回Collection目标类型。比较要求同类型或声明可转换同维度数；不把Bool当Int。加减同维度/同精度，乘除组合维度；Instant±Duration→Instant、Instant−Instant→Duration，Instant+Instant非法。除0、溢出、访问错误类型为error。除法结果精度按显式Decimal类型，不能取宿主float。Count有限Collection→Int，Sum数字集合→同单位数字；ForAll/Exists谓词Bool；If条件Bool且两分支有唯一最小共同类型，否则拒绝。集合操作无隐式笛卡尔积。

Known运算遵从类型语义。Null只允许IsNull或显式可空消除；普通比较/算术读到Null为error。Missing由IsMissing可观察；普通读为unknown(reason=missing)，required的结构义务另判violated。Unknown参与纯运算传播unknown。逻辑采用强Kleene：false AND unknown=false，true OR unknown=true，其余不确定=unknown；error优先于这两个吸收律。If只求选中分支，条件unknown时结果unknown，不推测分支。ForAll空集=true、Exists空集=false，但报告注明无见证；含unknown按AND/OR折叠。Filter任一谓词unknown则集合unknown，不能把不确定成员丢掉后Count。集合闭包未知则聚合unknown，即使观察计数暂未超界；明确已超上界可单独证伪结构基数。

`Constraint={id,context:type_ref,bindings:[{name,type}],applies:Expr,assertion:Expr,unless:Expr,diagnostic_targets:[Ref|Local]}`。三个表达式必须Bool。先求applies/unless：任一error→error；applies=false或unless=true→not_applicable；否则任一unknown→unknown；仅applies=true且unless=false求assertion，true/false→satisfied/violated。必要、充分不同：A要求B为A⇒B；“仅当”不是双向等价。约束合取保留逐项结果，不能用一个总Bool隐藏unknown/not_applicable/error。

## 操作、状态、过程与授权

`Operation={id,kind:query|command,input:Record,output:Type,errors:[{id,type}],pre:Expr,post:Expr,effects:[Effect],transaction:{scope:[ElementRef],isolation:serializable|version_compare},retry:{mode:none|idempotent,max_attempts},permission_ref:ElementRef}`。Effect为`Set{target,field,value}|Create{type,slots}|Delete{target,cascade}|Link{relation,participants}|Unlink{relation,participants}|Emit{event,payload}`。query effects须为空；效果引用必须在事务写集，读pre为旧状态、post同时绑定old/new，效果类型匹配。pre或权限非true即不执行；unknown返回indeterminate，不授权。post失败不得发布候选状态；事务边界外Emit使用明确outbox或补偿契约，不能承诺跨服务原子性。

`StateMachine={id,context,states:[id],initial:state_id,final:[state_id],events:[{id,payload:Record}],transitions:[{id,from,event,guard:Expr,effect:operation_ref,to,deadline:Duration?}]}`。状态引用存在，initial唯一；同一状态/事件同时可用多个迁移即conflict，未验证互斥不声称确定。事件到达时以一份状态版本检查权限、guard、deadline，单个事务更新；guard未知不选分支，过期返回timeout，旧版本conflict。有限轨迹的接受以终态定义，不能推出所有轨迹性质。

`Process={id,nodes:[Start|End|Action{operation_ref}|Branch{guards}|Fork|Join],edges:[{from,to}],join_mode:all|any,cancellation:{scope,compensation_refs},clock_ref:ElementRef}`。Start唯一、所有可达节点可达End；Branch恰有一个true，否则conflict/unknown；Fork复制控制token，Join按相同fork实例等待all或any，any必须取消未完成分支并按补偿记录。不同分支冲突写集由Operation隔离解决，不按布局顺序执行。截止与时钟单调语义由clock_ref绑定；未完成运行结果为pending/timeout，不能判进程终验通过。

Process节点的封闭形状为`Start{id}`、`End{id}`、`Action{id,operation_ref,input_bindings:[{parameter,expression}]}`、`Branch{id,guards:[{target:node_id,predicate:Expr}]}`、`Fork{id,join:node_id}`、`Join{id,fork:node_id}`。所有节点ID在过程内唯一；边仅引用本过程节点，Start入度0/出度1、End出度0、Action出度1，Branch每条出边恰有一个guard，Fork至少两条出边，Join入边匹配同fork的分支、出度1。结构化fork/join不能交叉，循环必须含显式Action且执行有步数/时限预算，运行耗尽保留timeout。token包括process_instance/fork_instance/branch_id，不能把不同业务实例的完成信号混合。节点只引用已经定义的操作，不内嵌代码。

`Policy={id,subjects:ElementRef,resources:ElementRef,actions:[ElementRef],rules:[{effect:allow|deny,condition:Expr}],combining:deny_overrides,default:deny}`。subjects/resources须解析为类型，actions须为Operation，permission_ref须为Policy，transaction.scope须为可寻址实体/关系声明；同包全部用Local。Operation→Policy→Operation是合法同包元素引用闭环，不是继承环或跨包哈希依赖环。所有匹配deny先行；unknown deny导致indeterminate；无deny且有true allow才permit；未知allow且无true allow为indeterminate，其余deny。未知不是permit。角色成员关系也是版本化输入，UI仅解释。外部调用`ExternalContract={id,capability,input,output,errors,timeout:Duration,idempotency,trust,observation_schema}`；无真实回执→unknown，超时→timeout，错误→error。ExternalObservation只读已绑定观测，无求值器暗中联网/重试；回执的请求/响应/时刻/服务版本/hash必须匹配。

## 质量、任务、视图与演化

`Quality={id,requirement_ref,metric:{name,unit,direction},workload_ref,environment_ref,aggregation:{kind:quantile|mean|all,p:?},threshold:Quantity?,method_ref,sampling:{count,window},acceptance:Expr?,unresolved:[question_ref]}`。quantile要求0≤p≤1，其他p=null；method定义分位算法、失败样本处理和全分母。threshold/acceptance缺失保留not_operationalized，不能由“易用”自动发明阈值。不同环境/负载/方法不合并统计，未观测→not_run，样本不足→unknown，阈值违反→violated。安全/隐私不因平均性能通过而获得许可。

`Task={id,goal,actor_ref,inputs:[type_ref],steps:[{id,operation_ref?,information_refs,success:Expr?,errors:[error_ref]}],acceptance_refs}`；`View={id,mode:review|business|change_review,task_ref,bindings:[{widget,element_ref,projection}],layout,accessibility,actions:[action_ref]}`。信息/动作均解析到语义引用；layout不参与领域规则hash，视图本身仍版本化。review可显示无效/未决候选，动作绑定候选和问题，不依赖应用命令；business动作须有CommandBinding，未绑定为design_only。

`Evolution={id,before:ArtifactRef,after:ArtifactRef,changes:[{element,kind,old,new}],trace_links:[{from,to,relation,evidence}],migration:{scope,pre,steps,post,losses,recovery},required_regressions:[ArtifactRef]}`。旧引用始终可解析，不自动重定向新版本。删除/收紧类型先检查旧实例；新增枚举值需要消费穷尽性重验；改规则使旧报告stale，依赖未知保持unknown。迁移逐步记录已执行、失败、恢复状态；无恢复实现为not_available，不能写rolled_back。文件变更须owner及expected_old_hash，混合所有权无合并算法则conflict，代码事实仅形成同步提案。

## 语义扩展与支持合同

日常领域声明仅实例化上述构造。真正新语义使用`SemanticProfile={id,version,hash,imports,features:[{id,payload_schema_ref}],operators:[{id,parameters,result,effects}],denotation_ref,composition:{requires,conflicts,bridges},evaluator_ref?,limits:{steps,time,memory},diagnostics,conformance_refs,migration_ref}`。必须给可判定良构规则、数学/操作解释及正反未知用例；只提供名字/执行器地址不合格。effects为pure|observed|command；pure表达式不能调用command，observed必须绑定观测。无唯一桥接的同名/重载语义冲突拒绝，不按加载顺序取胜。包是数据，不执行导入代码。

`Support={subject_ref,profile_ref,parse:exact|rejected,validate:exact|residual|unsupported,view:exact|annotated|unsupported,generate:exact|lossy|unsupported,reason,losses:[ref],residual_obligations:[ref],evidence:[ArtifactRef]}`。逐项支持而非整包“支持”。本页没有实现的族按此结构描述投影缺口，**其含义由上文定义，不由unsupported定义**。有损产物可用于查看，必要义务残余时不可授权应用交付。来源工具不同不自动保证独立。

详细[具体推演](language-cases.md)、[消费者载荷](consumers-0.2.md)及[有限配置](finite-domain-0.1.md)共同构成此次设计出口；运行事实与设计通过分开审核。
