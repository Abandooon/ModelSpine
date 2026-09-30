# 消费者合同 0.2-draft

公共引用/语言含义唯一见[language/0.2](language-0.2.md)。下列是封闭记录设计，字段全部必填，可空字段标`?`；尚未实现的消费者不能仅因本页存在记为可用。`A(x)=ArtifactRef(project_id="demo",artifact_id=x,revision="1",content_hash=SHA256(实际规范内容))`为本文载荷宏，实例化时必须计算hash；`E(x)=Ref(package="domain",version="1",hash=H(domain),element=x)`。凡接收报告的消费者都按自己先固定的definition/plan/scope/obligation列表重核绑定，不接受报告自行减小分母。

## 定义、实例与验证器

独立ProjectModel必须存在的条件：用户要求项目设计对象/配置/流程实例、验证某实例符合性、示例/反例执行、项目级约束、带种子数据/租户配置生成、迁移既有设计或应用数据。领域定义里的类型不是实例，不能拿Entity.name冒充项目对象。

可以省略：仅构建可复用领域语言、展示类型/规则的审阅、生成只依赖定义的类型/序列化骨架，且无实例级配置或验收义务。此时`project_model=null,project_model_reason="definition_only_no_instance_obligations"`，实例结果not_run，不伪造空项目。运行数据可在应用启动后创建，不意味着必须预造业务实例；若ApplicationSpec可自行完整表达项目配置，可不另造重复ProjectModel，但必须列`configuration_owner="application_spec"`及配置/义务引用。示例模型与被交付项目模型须用purpose区分，示例通过不等于项目通过。

```text
ValidatorSpec={id,version,definition_ref,profile_ref,input_layer:project|runtime_trace,
 obligations:[element_ref],scope:[element_ref],assumptions:[ArtifactRef],
 implementation_ref,parameters,budget:{steps,time_ms},support:[Support]}
ValidationRequest={candidate_ref,project_model_ref,validator_ref,scope,obligations,assumptions}
ValidationResult={request_hash,definition_ref,project_model_ref,validator_ref,
 scope,obligations,outcomes:[{obligation,target,status,reason,evidence}],
 tool_ref,run_ref,requirement_fidelity:not_checked|independently_checked}
```

具体消费：`definition=A(domain),project=A(positive),validator=A(finite-domain-checker),scope=[E(item)],obligations=[E(enabled),E(enabled-rule)]`；positive对象enabled=true→字段/规则satisfied；negative false→规则violated；unknown slot→unknown。若required字段缺失，结构violated，规则error；错definition hash→conflict，无检查结果。验证器文件存在、未执行→not_run。完整范围仍含required Residual，则unknown；不能用可执行子集全绿称整模型合规。本轮实际有限report/API见finite-domain-0.1，完整ValidatorSpec编译/代码生成仍设计。assurance负责计划与结果责任，适配器执行，kernel只核对接受所需绑定。

## 代码前审阅与回答

```text
ReviewInput={id,version,review_ref,mode:review,request_ref,candidate_ref,
 definition_ref?,project_examples:[{model_ref,purpose:example|counterexample}],
 traces,issues,reports:[ArtifactRef],support:[Support],unrenderable:[{path,raw,reason}]}
ReviewAction={id,project_id,view_ref,expected_review_ref,expected_request_ref,expected_candidate_ref,actor_ref,
 action:answer|decline|confirm|propose_edit,question_ref?,targets:[element_ref],
 answer_text?,proposed_values?,reason}
ReviewResult={action_ref,status:recorded|already_recorded|conflict|invalid|cancelled,
 next_candidate_ref?,next_question_refs:[ArtifactRef],checks:[ArtifactRef],diagnostics}
```

例：candidate A(c1)有issue q1“上限是否含历史记录”；ReviewAction答“仅当前”绑定项目、请求、A(c1)/A(q1)及预期review_ref，requirements追加回答版本。只有真实修订产物存在才可报告A(c2)；本轮没有自动修订，next_candidate_ref=null、revision_status=pending，不复制旧候选冒称新候选。即使candidate没变，回答后的旧review_ref也冲突，不自动套用。decline保留issue；confirm只登记目标确认，不把检查改satisfied或清除其他未决。修改layout用View新版本，不修改definition hash；非法规则原载荷保留。实现责任：interaction呈现/解释、requirements保存回答/候选、编排重检；无CommandBinding或已接受模型也是合法输入。

候选工件引用必须钉住外部响应**原始字节**，与definition_ref分开：同definition但issues/traces或序列化原件变化，candidate_ref必须变化。问题身份绑定候选原件及原始来源、issue ID，不按问题文本合并。审阅状态有独立版本/hash；动作ID同规范内容重试返回already_recorded，异内容conflict。回答/拒答/编辑是独立actor动作来源，不能伪装SourceSpan或倒写原文真实性。

上述是完整消费者设计；当前实际可调用子合同为 [model-review/0.1](../../requirements/contracts/review.md)，共享动作类型在protocols.review，纯状态/解释归requirements.review，本地保存归apps/model_review.py。其confirm.targets为有限ID字符串或专用整体标识`review:candidate`（冒号在finite ID中非法）；合法元素`$candidate`只表示该元素，与整体确认不同。完整候选propose_edit保留原字节、旧绑定、修改理由及结构诊断，只作为待采纳提案，不替换当前有效候选；允许用户提出删除约束/residual、改变AND/OR等需求变化，但不能据结构合法自动确认意图。持久化/恢复与D精确函数载荷见该子合同，完整消费者设计的其余操作仍未实现。

## ApplicationSpec与生成

```text
ApplicationSpec={id,version,requirement_refs,definition_ref,project_model_ref?,
 project_model_reason?,configuration_owner:project_model|application_spec,
 configuration:[{id,type_ref,value,source_ref}],tasks:[Task],views:[View],
 operations:[element_ref],policies:[element_ref],data:{stores,transactions,retention,migrations},
 integrations:[element_ref],quality:[element_ref],topology,public_acceptance_refs,
 unresolved:[{id,question,source_ref,required}],confirmation_refs}
TargetProfile={id,version,family:web|desktop,backend_ref,toolchain_refs,
 templates:[ArtifactRef],runtime_refs,platform:{os,arch},support:[Support],
 build_entry,run_entry,test_entry,package_entry,resources,permissions}
GenerationUnit={id,input_refs,obligations,mode:template|llm|composition,
 interface:{inputs,outputs,errors},pre,post,allowed_paths,allowed_dependencies,
 acceptance_refs,budget:{attempts,time_ms,tokens?,cost?},template_ref?,model_ref?}
GenerationManifest={id,version,spec_ref,target_ref,plan_ref,units:[{unit_ref,
 inputs,outputs,control_stage,receipt_ref,status}],files:[{path,owner,
 expected_old_hash?,new_hash,unit_ref,trace_refs}],residuals}
```

具体ApplicationSpec的完整展开如下（JSON，无A/E宏、省略号或别名字段）。这是**封闭结构有效、需求未完成、引用待解析**的设计载荷，不是已批准的生成输入。domain的64位a是本例调用方给定的域身份，假设域含operator/machine/run/run-policy；本文未附该域原字节，绑定验证保持not_checked，不能将示例hash称为真实制品证明。requirements引用对应下面这段UTF-8原文字节（不含末尾换行），可以独立复算hash：

```text
Operator may start a ready machine. Use a remote durable store. Retention and success criteria need clarification.
```

```json
{
  "id": "machine-app",
  "version": "1",
  "requirement_refs": [
    {
      "project_id": "demo",
      "artifact_id": "requirements",
      "revision": "1",
      "content_hash": "29e13cb8cc7771b5e056373efef57222bcd31ccf2452a23f295031ed3f2b4ae3"
    }
  ],
  "definition_ref": {
    "project_id": "demo",
    "artifact_id": "domain",
    "revision": "1",
    "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "project_model_ref": null,
  "project_model_reason": "configuration_in_application_spec_no_design_instances",
  "configuration_owner": "application_spec",
  "configuration": [],
  "tasks": [
    {
      "id": "start-machine",
      "goal": "Start a ready machine",
      "actor_ref": {
        "package": "domain",
        "version": "1",
        "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "element": "operator"
      },
      "inputs": [],
      "steps": [
        {
          "id": "start-step",
          "operation_ref": {
            "package": "domain",
            "version": "1",
            "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "element": "run"
          },
          "information_refs": [
            {
              "package": "domain",
              "version": "1",
              "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              "element": "machine"
            }
          ],
          "success": null,
          "errors": []
        }
      ],
      "acceptance_refs": []
    }
  ],
  "views": [],
  "operations": [
    {
      "package": "domain",
      "version": "1",
      "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "element": "run"
    }
  ],
  "policies": [
    {
      "package": "domain",
      "version": "1",
      "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "element": "run-policy"
    }
  ],
  "data": {
    "stores": [
      {
        "id": "main",
        "model_refs": [
          {
            "project_id": "demo",
            "artifact_id": "domain",
            "revision": "1",
            "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
          }
        ],
        "persistence": "durable",
        "location": "remote",
        "source_ref": {
          "project_id": "demo",
          "artifact_id": "requirements",
          "revision": "1",
          "content_hash": "29e13cb8cc7771b5e056373efef57222bcd31ccf2452a23f295031ed3f2b4ae3"
        }
      }
    ],
    "transactions": [
      {
        "operation_ref": {
          "package": "domain",
          "version": "1",
          "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "element": "run"
        },
        "store_ids": [
          "main"
        ],
        "isolation": "version_compare",
        "atomic_scope": [
          {
            "package": "domain",
            "version": "1",
            "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "element": "machine"
          }
        ]
      }
    ],
    "retention": [],
    "migrations": []
  },
  "integrations": [],
  "quality": [],
  "topology": {
    "nodes": [
      {
        "id": "ui",
        "role": "client",
        "location": "browser"
      },
      {
        "id": "api",
        "role": "service",
        "location": "server"
      },
      {
        "id": "db",
        "role": "store",
        "location": "server"
      }
    ],
    "channels": [],
    "source_refs": [
      {
        "project_id": "demo",
        "artifact_id": "requirements",
        "revision": "1",
        "content_hash": "29e13cb8cc7771b5e056373efef57222bcd31ccf2452a23f295031ed3f2b4ae3"
      }
    ]
  },
  "public_acceptance_refs": [],
  "unresolved": [
    {
      "id": "retention",
      "question": "How long must stored data be retained?",
      "source_ref": {
        "project_id": "demo",
        "artifact_id": "requirements",
        "revision": "1",
        "content_hash": "29e13cb8cc7771b5e056373efef57222bcd31ccf2452a23f295031ed3f2b4ae3"
      },
      "required": true
    },
    {
      "id": "success",
      "question": "What result and errors define successful run?",
      "source_ref": {
        "project_id": "demo",
        "artifact_id": "requirements",
        "revision": "1",
        "content_hash": "29e13cb8cc7771b5e056373efef57222bcd31ccf2452a23f295031ed3f2b4ae3"
      },
      "required": true
    },
    {
      "id": "transport",
      "question": "Which versioned protocols connect client, service and store?",
      "source_ref": {
        "project_id": "demo",
        "artifact_id": "requirements",
        "revision": "1",
        "content_hash": "29e13cb8cc7771b5e056373efef57222bcd31ccf2452a23f295031ed3f2b4ae3"
      },
      "required": true
    }
  ],
  "confirmation_refs": []
}
```

这里ProjectModel省略的理由是没有独立设计实例，配置责任在ApplicationSpec。未决定的保留期、成功/错误判据和通道协议分别保留required unresolved；retention/channels/acceptance空数组只表示尚未设计，不表示无需该义务。未完成spec可被审阅，生成/交付就绪必须拒绝；还须解析域引用、补齐公开验收与必要确认，不能由目标后端选默认值。API/模型预算缺失保持unit未运行。

逐项非法变体（在上述载荷上仅改指定位置，其余字节保持）：

|变体|确定的拒绝原因|
|---|---|
|transaction把operation_ref改为operation、atomic_scope改为scope|封闭字段集不符：unknown operation/scope，missing operation_ref/atomic_scope|
|transaction.store_ids改为["missing-store"]|形状合法但引用未声明store，invalid；不得创建默认store|
|Task把actor_ref改actor，steps改["run"]|unknown actor/missing actor_ref，step不是规定的记录；inputs/goal/acceptance_refs不能省略|
|topology改为{"client":"browser","service":"server","storage":"server"}|unknown client/service/storage，missing nodes/channels/source_refs|
|将channels填为[{"from":"ui","to":"missing-node","protocol_ref":给定引用,"trust_boundary":true}]|目标节点未声明，invalid；协议引用未知不等于存在|
|删除required unresolved并宣称可生成|没有保留期/成功判据/协议的需求解决证据；即使JSON形状合法，需求就绪不能通过|

这组校核只检查设计载荷及明确未决责任，不新增运行ApplicationSpec解码器或E执行器。

模板单元`id:types,mode:template,inputs:[A(domain)],outputs:["src/types.py"],allowed_paths:["src/types.py"],obligations:[E(type-serialization)]`；LLM单元`id:run-body,interface={input:{expected_version:Int},output:RunResult,errors:[forbidden,conflict]},pre=run-policy,post=ready_to_running,allowed_paths:["src/run_body.py"],allowed_dependencies:[],budget:{attempts:1,time_ms:60000,tokens:明确值,cost:明确值}`。必须由调用方填真实预算，本文数值只是时间示例，非真实调用授权。接口越权写`src/auth.py`→invalid；删除权限检查→义务violated；模板失败→error，不能自动换LLM。生成器自编测试仅开发检查，不可充当全部独立终验。

ApplicationSpec只含公开验收合同，保留评价的原文期待、实例答案和判据不得进入提示、模板、修复。正式采用前固定plan/obligation集；需要修改原需求则开新任务版本，不能让修复器自行减少分母。

ApplicationSpec.data中的store为`{id,model_refs,persistence:volatile|durable,location:local|remote,source_ref}`；transaction为`{operation_ref,store_ids,isolation,atomic_scope}`；retention为`{store_id,duration,delete_operation_ref,source_ref}`；migration为版本化MigrationPlan引用。topology为`{nodes:[{id,role:client|service|store,location}],channels:[{from,to,protocol_ref,trust_boundary}],source_refs}`。未决定的字段用对应unresolved条目表达，不能将未决字符串当成已选技术栈名。配置value按type_ref检查，参数parameter/value按输入Record检查；layout、accessibility、observations、环境与平台特定参数使用`{schema_ref:ArtifactRef,value}`，schema_ref必须在所选profile闭包内且有严格字段/类型定义，不允许不带schema的万能JSON逃生口。本轮未选择具体UI或构建profile，因此这些目标载荷不能当成已可执行配置。

## 同一义务的Web/桌面消费

共同义务：E(run-policy)与E(ready-to-running)均要求operator、未停用、ready状态和expected_version比较。数值/时间/枚举等序列化由同一类型规范提供。

|字段|Web映射载荷|桌面映射载荷|
|---|---|---|
|命令|`{operation:E(run),transport:"HTTP",entry:"POST /machines/{id}/run",actor_source:"authenticated_session",version_field:"expected_version",executor:"service"}`|`{operation:E(run),transport:"IPC",entry:"machine.run",actor_source:"authenticated_local_session",version_field:"expected_version",executor:"application_service"}`|
|任务/视图|`{task:start,view:"machine-page",state_source:"service_response",errors:[403,409]}`|`{task:start,view:"machine-window",state_source:"IPC_response",errors:[forbidden,conflict]}`|
|权限边界|API服务原子重核policy+state，隐藏按钮仅解释|IPC服务重核policy+state+OS能力；renderer不能直接写业务库|
|平台义务|`{origin_policy:"explicit",session_protection:"explicit",disconnect:"show_unknown"}`|`{os:"declared",arch:"declared",file_access:"explicit_paths",device_access:"none",ipc_validation:true,upgrade_data_check:true}`|
|交付|固定构建/服务/浏览器环境、启动日志、业务路径回执|固定OS/架构、安装/启动、IPC/文件边界、更新与数据迁移回执|

正：双方以同一状态版本完成ready→running，权限拒绝/冲突均保持状态。反：Web只在浏览器检查角色或桌面renderer直写状态，Support不能报exact；桌面后端丢expected_version是lossy且阻交付。未知：只有代码或截图、无服务/IPC运行记录→not_run；Web成功不填桌面成功。平台选择只映射明确需求，不推测离线、存储或许可要求。

```text
ApplicationBuild={id,manifest_ref,source_ref,dependency_refs,environment_ref,
 commands:[{argv,cwd,started_at,ended_at,exit_code,stdout_ref,stderr_ref}],
 build_status,launch_status,business_results,interaction_results,package_status,
 artifacts:[ArtifactRef],residuals,delivery_status}
```

构建返回exit_code=1即build failed，launch=not_run，无delivery success；launch失败不能用旧二进制冒充；内部类型/业务自测全部通过而公开原文任务失败，business_results仍violated，完整分母保留。此合同没有自动部署或发布授权。

## 维护与来源试验

```text
MaintenanceRequest={id,old_spec_ref,new_requirement_ref,base_model_ref,
 old_manifest_ref,observed_files:[{path,hash,owner}],data_version,trace_coverage}
MaintenancePlan={id,request_ref,new_spec_ref,affected_units,unchanged_obligations,
 changes:[{path,owner,expected_old_hash,operation,new_hash?}],
 model_migration,data_migration,regressions,recovery:{available,scope,steps}}
MaintenanceResult={plan_ref,model_commit_ref?,files_written,files_rejected,
 migration_outcomes,build_ref?,regression_results,recovery_result,residuals}
SourceTrial={id,source_ref,license_ref,environment_ref,input_definition_ref,
 target_ref,mapping:[Support],commands,dependency_cost,outputs,residuals,decision}
```

维护例：cap3→2，old_instance.count3，文件src/run_body.py owner=human/hash=h2、计划expected=h1。先暴露旧数据违反及文件conflict，保留旧运行版本；没有迁移/合并/恢复实现不报告已更新或rolled_back。成功条件是新count2行为与未变权限回归实际运行通过、人工文件不被覆盖，模型保存/代码构建/迁移/交付分点记录。trace_coverage=unknown时受影响集合不能空推断无影响，code-intelligence负责指出未知，kernel负责报告适用性。

C一次试验输入：公开`finite-domain-examples.json`和finite-domain/0.1固定合同；精确绑定每个definition hash。只试一个来源和一个Web目标，记录真实源码/工具版本、命令、安装/运行时间及输出/拒绝。SourceTrial.mapping按实体、字段、关系、规则逐项给exact/lossy/unsupported与证据；若来源能保存关系但生成目标不能检查基数，则parse exact/generate lossy/residual obligation明确，不能整体采用。正样例结构消费、反样例规则/基数违反、未知样例与必需Residual都进入分母。来源声明支持不等于本平台运行支持，不要求C同时实现全部族。
