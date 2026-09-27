# BESSER 有限来源适配试验

2026-09-28，交付待总领审核。结论为**条件采用结构投影与 Web 模板作为候选来源；不采用生成端作为领域语义保障**。本次前端构建和 localhost HTTP 服务成功，后端依赖下载失败且启动失败。没有业务链、浏览器交互、自然语言输入或 F1/F3 验收，不能称完整接入或产品交付。

固定来源：[BESSER 提交 9cf7a90928f44dabbe418dab69879014319ee38e](https://github.com/BESSER-PEARL/BESSER/tree/9cf7a90928f44dabbe418dab69879014319ee38e)，setup.cfg 为 7.18.0，LICENSE.md 为 MIT（2023 BESSER-PEARL）。唯一目标是 `besser.generators.web_app.web_app_generator.WebAppGenerator`；内部调用 React 与 Backend 是该目标自带链路，没有切换来源/框架。生成代码仅留隔离目录，未把外部源码、依赖或应用放入生产 apps；未安装 BESSER 全发行包。

规范输入为 [finite-domain/0.1](../packages/protocols/contracts/finite-domain-0.1.md) 和[公开工程例](../packages/protocols/contracts/finite-domain-examples.json)。language/consumers-0.2 仅提供总体责任。有限合同与例子的原字节 SHA256 分别为 `4fdeed991f064e386754727d0da869c4ee66843f272f96e6a3e0eae67c9c32db`、`e37d3dc6f0d7145e4bc5373fa73e19637d3943590df6421a7c386fe6020eff2d`；开始/结束未变化。公开定义规范哈希为 `88f4510641d59a5b59d915f825c37f6eb8a46f9e5e2f6d3e5cfa34d1b387ace3`。

接口见 [besser_finite.py](../adapters/besser_finite.py)：

- `project_definition(definition, reference)`：复用公共严格类型/良构校验及 `validate_artifact_ref`（含非空项目身份），核对定义 ID/版本/哈希，返回 B-UML 模型与逐项支持报告；不执行 ProjectModel。
- `generate_web_trial(definition, reference, output_dir)`：只向新目录生成诊断候选和 `modelspine-support.json`；目录已存在则拒绝。生成异常传播，部分文件保留，`generation_status=started` 不能当作成功。
- 宿主须将已核对的固定干净来源放入 Python 搜索路径。适配器不自行安装、发现或验证任意 BESSER 分发包；本试验宿主逐次核对 Git HEAD 与干净状态，另记录实际导入文件及模板哈希。`source_commit` 是此固定试验的来源约束，不能作为任意调用者的独立来源证明。

所有显示名称和原始定义保存在报告中；目标标识符由排序后的本地 ID 生成，避免显示文本变成代码。编号只在当前定义哈希内稳定，不提供跨版本代码维护。报告始终 `delivery_eligible=false`，不靠布尔配置解锁产品交付。

|义务|结构投影|Web 生成/实际观察|
|---|---|---|
|单包实体、三标量|Class/Property、明确 ID→目标名映射；必填非空字段基本结构可保持|目标存在类型转换，身份/版本/部分信息不保持；integer 有 Int64 缺口；标记 lossy|
|可选与 nullable|Multiplicity(0/1,1) 和 is_optional；原声明完整保留|目标混同可选/可空，Missing/Unknown 无独立表示；lossy|
|二元关联双向端点|source 端使用 sources_per_target，target 端使用 targets_per_source；有限界可表达|上下界、distinct、人口闭包并未由 Create 模型实现；lossy|
|unbounded / 9999|BESSER `*` 存为 9999；报告明确 lossy|不能称真正无限；不据此放行|
|最大值 0；unbounded 且下界>9999|来源不能构造，明确 unsupported|拒绝，不扩大上界|
|必填非空整数与常量的无条件 eq/lt/le|尝试 Constraint(OCL)，仅 Known Int64 输入范围|本次实际运行 le：1/0 接受、2 拒绝；eq/lt 未单独动态验收；Create 之外未验，整体仍 lossy|
|条件/count/logic/is_null/nullable 比较|本适配器保留完整 AST；unsupported|不宣称所有 BESSER 路径均不支持，只报告本映射未接入；公共 active-cap 不编译|
|显式 Residual|完整保留 id/family/text/required|逐项 unknown；必需残余阻止完整支持|
|继承/跨包/未知 op/非法引用|由公开严格边界拒绝直接载荷|不伪装成已执行结构|
|错定义版本/哈希|在来源构造前 conflict|不接受旧绑定|

公开样例的独立核对使用合同期望、源对象端点检查和真实生成 Pydantic 类，不调用 A 的规则求值器，也不读取 B 评价目录。

|公开输入|期望/义务|实际观察|
|---|---|---|
|positive|active-cap satisfied|Create 接受；不能据此证明条件规则已实现|
|negative|active-cap violated|Create 接受两条关系，遗漏规则|
|unknown|unknown|没有未知值投影；未送入目标，not_run/unsupported，不转换成 null/default|
|not-applicable|not_applicable|Create 接受，目标没有该结果状态|
|open-population|unknown|目标不表达人口闭包；not_run/unsupported|
|zero-links|基数 violated|Create 接受空关系列表，遗漏下界|
|residual_definition / residual_project|time-window 必需残余 unknown|定义投影保存残余；实例不执行，不声称满足|
|scalar_projection_positive|旧标量投影正例|用于字段边界及派生整数探针；不是自然语言验收|
|scalar_projection_rejected_definition|旧标量内核拒绝关系/规则|对 BESSER 是可带残余投影，与旧内核拒绝不矛盾；完整 Web 交付仍拒绝|
|invalid_definition_patch / wrong_version_project_patch|invalid / conflict|非法端点及同类定义引用错版本/哈希拒绝；不提供 ProjectModel 导入 API|

额外公开整数探针实测：`true` 被强制转换成 `1`、`-9223372036854775809` 被接受；缺必填字段与 nonnullable null 被拒绝。可选缺失读取/is_null 和 Null×Unknown 比较均留作 unsupported，不借目标普通空值行为宣称符合 finite 语义。A 返修检查器 SHA256 已实际核对为 `4a0815aaf81a4cde83c58092a84dc451c698ae0a21ab7f578c45ad0b5d4a5d35`；在 C 中仅作经审核接口基线，未导入/执行。

实际工具链：Windows、Python 3.12.14、Node 24.20.0、npm 11.19.0；构建实际 Vite 5.4.21。生成器初始安装 Jinja2 3.1.6、ANTLR runtime 4.13.2、docker SDK 7.1.0、Pydantic 2.12.5，连同传递依赖共 15 个 Python 分发。docker SDK 是 BackendGenerator 的导入依赖，不表示启动 Docker；未安装 NN、agent、数据库驱动全套或调用 LLM。

一次 Web 目标用公开关系输入及独立整数边界输入分别生成 43/42 个文件（含支持报告）。公开前端 npm 安装 173 个包，使用 `--ignore-scripts`，没有修改生成 package.json；实际 package-lock.json 已保存。只在该前端构建并短暂启动 Vite preview：首页和 JS 资源 HTTP 200，随后进程结束。界面只含诊断说明，未生成业务任务 UI；HTTP 成功不是浏览器交互成功。

后端按生成 requirements.txt 安装时 TLS EOF；同配置一次重试再次 TLS EOF。未换索引、关闭 TLS 校验或借全局环境填补。实际执行 main_api.py 因缺 FastAPI 退出 1。前端成功不掩盖此失败，后端事务、API、业务与持久化均未验。

主要实测命令耗时：联网取源码 67.933 秒；venv 5.989 秒；生成器依赖安装 15.700 秒；公开/整数生成 1.520/1.312 秒；前端安装 64.182 秒、构建 2.019 秒、含进程管理的 HTTP 探针 0.833 秒；后端安装失败 5.793 秒、唯一重试失败 6.332 秒、启动失败 0.165 秒。均为宿主 `perf_counter` 墙钟，包含启动开销，不是算法基准。人工设计/修正成本及磁盘/带宽费用未测；无付费模型调用。

工程测试见 [test_besser_adapter.py](../tests/test_besser_adapter.py)。常规无 BESSER 环境中，来源集成测试显式 skip，不能算已通过；本次隔离来源环境中最终 10 项全部实际执行。初次 8 项有 1 项测试错误（误以为 model.types 不含原语类型），原失败日志保留；修正测试定位后通过，未改外部实现或放宽语义判据。总领随后独立发现空 project_id 未经公共引用完整性校验的真实适配缺陷；已改用 `validate_artifact_ref` 并增加拒绝回归。修前产物及哈希仍保留，修后身份单列在 `final-verification.json`，不改写旧运行。

采用代价：生成服务还需严格标量/Int64 边界、部分值处理、事务内双向基数及条件规则、义务绑定/拒绝、真实任务 UI、身份/版本与维护保护；本试验没有实现这些。条件采用仅限已有模板/结构构造的候选复用，当前生成应用应拒绝作为领域有效产品。下一入口为总领阅读实际 diff、映射和运行日志，决定是否将此候选交后续开发；基础产品仍返回同一真实 F1 项目合流。不能从本试验推导比较优势。

研究工作区证据位于 `artifacts/runs/besser-adaptation/2026-09-28/`：`trial-result.json` 为索引，`source-inventory-recaptured.json` 为完整来源/导入/模板/依赖清单，另有输入锁、支持报告、生成文件哈希、安装日志/前端锁与逐命令回执。首次 `provenance.json` 被同名命令宿主的回执覆盖，原详细清单已丢失；保留现有回执与 provenance.log，不以摘要恢复原证据。新清单于 2026-09-28 01:39:58（Asia/Shanghai，精确 UTC 见 captured_at）重新捕获，是修复后环境的观察，不冒充首次运行时快照；未重跑生成或安装。记录器现已拒绝覆盖子命令运行中创建的同名回执文件。公共代码仓库不携带该研究目录、整包来源或生成应用。
