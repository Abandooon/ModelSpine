# 有界真实语言入口（typed-language-run/0.3）

`apps/language_modeling.py`将一个原文ModelingRequest经现有typed提示、单一Responses适配器、已有typed检查、A审阅保存交给[本地审阅UI](model-review-ui.md)。这是P1-R2有限入口，不包含自动修复、回答驱动修订、实例生成/检查、提案采纳或应用生成；结构合法不等于原文忠实。生产代码不读取研究样本或独立答案。

协议固定为`POST https://api.openai-proxy.org/v1/responses`、`gpt-6-luna`。供应商[兼容说明](https://doc.closeai-asia.com/tutorial/api/openai.html)声明支持无状态Responses；[官方参数](https://developers.openai.com/api/reference/python/resources/responses/methods/create)定义input、store、stream、max_output_tokens及响应状态/usage。请求带model、装配后的typed提示input、store=false、stream=false、max_output_tokens，以及固定`text.format={"type":"json_object"}`；不传previous_response_id、工具、温度或额外推理设置。prepare和执行重建均固定同一格式，不提供text回退开关。

0.3仅增加[Responses JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs)，完整保留0.2/SRC-01提示。官方合同约束可解析JSON，不保证typed schema，且仍须处理不完整等边界；本入口继续使用已有typed检查，不新增Schema层。供应商的一般兼容声明及官方模型能力不能证明当前代理实际执行该格式，尚须真实观察；即使返回合法JSON也不能证明内部约束实现或原文忠实。HTTP400不支持参数、refusal、不完整响应、completed但非法JSON或typed不合法均沿用停止与原件保留规则，不自动改参数再试。拒答content不被提取为候选，记录unsupported_output_shape；可提取但非法的候选仍供审阅。

## 配置与准备

仅标准库，无SDK/自动重试。宿主显式提供公开仓库外的绝对`.env`路径，进程只解析六个精确名称：MODELSPINE_PROVIDER_URL、MODELSPINE_BASE_URL、MODELSPINE_API_KEY、MODELSPINE_MODEL、MODELSPINE_MAX_REQUESTS、MODELSPINE_MAX_OUTPUT_TOKENS。值必须完整，模型和端点必须上述显式值；本计划请求预算1–20、每次输出上限1–40960（包括服务计入的推理输出）。prepare接受显式1或2个请求，数量不得大于配置预算；空输入、超过2个输入、重复请求或空任务身份拒绝。不得打印配置文件或把key放进命令行、提示、工件及公开仓库。TLS保持验证，urllib使用宿主已有系统/环境代理；不关闭TLS、不换域名，全部重定向拒绝。

先用[原文入口](domain-modeling.md)为原文准备request.json，再执行下列命令（工作目录platform）；双输入计划再增加`--request request-2.json`。不要求人工正确候选。目录父路径须存在，run-dir必须为新绝对路径，重复准备拒绝覆盖。

```text
python -B -I apps/language_modeling.py prepare --env-file "E:/private/.env" --run-dir "E:/runs/explicit-task" --task-id "explicit-task" --request request-1.json
```

prepare不联网。它保存每份原文的完整UTF-8（包括尾LF）、规范ModelingRequest、精确装配提示和无认证头的实际请求JSON。plan.json绑定请求、原文、提示/提示版本、请求参数、实际1或2个顺序slot、方法源码SHA及显式预算，返回plan_sha256。两请求不共享对方原文、响应或参考答案。原始请求文件的JSON排版不作为候选来源，保存的request.json是既有dumps规范编码，原文source.txt保持原字节。

宿主可先用假key和公开配置离线prepare，task_id绑定预算提案及历史收据；最终真实release再绑定精确plan SHA和唯一账本，不回写plan制造循环。prepare不等于释放预算。旧批次耗尽后，新目录不会自动产生额度，须另有明确新批次授权。有限批停止后，已有合法自动候选即可交独立评价；若只有第一份合法，执行其可用部分，缺失来源/配对及其他不可用分母保持not_run，不要求两份都合法才开始评价。

装配提示`typed-language-assembly/0.1`完整保留既有typed_modeling_prompt前缀，然后追加固定通用输出说明和SOURCE_LINES_JSON。行表使用与检查器相同的`request.text.splitlines()`、一基行号和精确行文本，不把CRLF、空行或Unicode行分隔的显示当作新需求；证据按选中完整行精确以LF连接，不加行号前缀，也不在该join结果之外额外加换行；选中末行为空时join产生的末尾LF必须保留。原始source.txt不归一化。行表明确是数据，不能提供业务参考模型。要求紧凑JSON、短ID、无缩进/围栏/重复解释，但不得省略必要键、原文条件、例外、未决、问题或残余，也不得缩短quote。宿主不修回模型的引文/行号或JSON；既有typed检查仍可拒绝它。此呈现调整不保证在配置的输出预算内得到完整或忠实候选。

## 明确执行与停止

确认最终计划后，每执行一次命令最多发送一次POST；本轮审核前不得执行：

```text
python -B -I apps/language_modeling.py execute-next --env-file "E:/private/.env" --run-dir "E:/runs/explicit-task" --expected-plan-sha256 "<prepare给出的hash>"
```

执行前再次核对计划hash、方法源码、配置、全部冻结输入的hash及各自重新构造的实际请求，包括尚未调用和已经调用的slot。每次先在对应attempts/001或002排他创建reservation.json并fsync，再联网。该目录是本计划唯一账本，失败和无响应均占用；重启不重置，不允许通过换目录重建同一任务来重置预算。最多执行已冻结的slot数，reserved_revision_slots只记录配置中未分配的额度，不授权自动调用。单输入/预算1在一次后即耗尽；新进程亦不可发送第二次。跨子批累计预算由宿主明确登记已耗/剩余，并以task_id引用预算记录身份；本入口不提供跨任务预算服务，不能借新目录抹去旧失败。不得自动循环、修JSON、删除围栏、补默认候选、换模型或换API。

单写者以.run.lock互斥。挂起锁、未完成attempt、receipt/工件损坏都拒绝继续；宿主须先核查是否已经发出或扣费，再另行决定恢复，不能删attempt假装没有消耗。receipt和其hash排他保存；写失败不返回成功，不退回旧缓存。无法持久化联网结果时已有reservation仍保留，调用完成状态为未知。预算不防恶意宿主删除整个账本或伪造所有hash，宿主负责独占目录及原证据保护。

继续前还通过公开read_review重开此前各成功attempt的review-project，由原存储层校验pending/busy、保存hash和动作重放；失败返回review_recovery_failed，不创建下一reservation或POST。装配层核对不可变request_ref与冻结请求、candidate_ref与receipt及candidate.raw，错绑定返回review_binding_conflict。合法answer等动作可以改变review_ref，不要求等于初始收据版本，也不据此声称候选已修订或语义通过。检查发生在各存储锁内的读取时点，不是跨审阅与联网的分布式事务；宿主继续负责运行期间目录及不可变原件不被外部替换。

传输设置1200秒socket超时，并在读取块间核对1200秒经过时间；不是精确总墙钟截止，单次阻塞读可使总耗时再增加一个socket超时。响应体上限2MiB，超限/网络失败/超时/HTTP非200/截断均保存已收到字节并停止。使用标准库HTTPResponse.read1逐段保留正文，避免填满read(amt)期间超时丢失已到达前缀；EOF时Content-Length尚未满足即truncated_http_body，即使已收正文恰好是完整JSON也不提取候选。正常长度、无Content-Length的正常EOF及完整chunked传输仍可接收。HTTP IncompleteRead保存此前前缀加异常partial，不修正文。任何已有失败、错模型、缺usage、不完整生成或拒绝候选都会停止后续slot；生成预算保留完整分母。

## 信封、候选与审阅身份

response.body为HTTP响应体，与候选分开。提取只接受Responses object、一个assistant message的一个output_text（可伴随reasoning项），不拼接多个答案/工具结果、不替换拒答为空候选。content.text按UTF-8编码保存为candidate.raw；它是JSON字符串解码后的精确文本字节，不冒称其与HTTP信封字节相同。不可提取时只有信封和失败收据，不伪造审阅候选。

能提取的非法/错绑定/截断JSON仍保存，并经既有create_review创建review-project；其检查调用inspect_typed_candidate，拒绝原件也可显示。inspection.json沿用generation_provenance=not_verified、requirement_fidelity=not_checked、instance_conformance=not_run。receipt另外说明真实transport观察、请求/返回模型、HTTP及Responses完成状态、实际usage、时间、字节身份；不把传输收据改写成语义认证。缺usage记录unknown/null，计价未核定则cost=null/not_measured，不填0。

服务若回显凭据，识别到的原文/JSON转义/嵌套JSON回显会在落盘前脱敏；ASCII凭据的原文字符、JSON短转义与Unicode转义混合匹配不依赖外层JSON完整，缺末括号或字符串被截断也可识别已完整出现的凭据。JSON字符串及其已收到的完整字符前缀最多解码4层用于识别，覆盖截断外信封中output_text等嵌套JSON字符串的混合转义回显，包括外层字符串尚未结束的情况。命中后保留实际结束符或未完成转义尾部，不补齐保存的字符串或外信封。这不是任意编码或无限嵌套识别器。receipt区分received_sha256与stored_sha256及response_bytes=redacted，并停止，不把脱敏工件称原始响应或送入候选链。异常日志只给本地固定错误码，不回显远端异常内容。不得将凭据主动发入输入；准备/执行都有检查。

receipt中的review_project可直接交给D：

```text
python -B -I apps/model_review_ui.py --project-dir "<receipt中的review_project>"
```

候选hash在提取、检查、审阅candidate_ref及UI的base64原件间核对；definition_ref不能替代候选身份。UI保存后仍为未确认候选，未决/不支持不被清除。

## 验证与当前事实

2026-10-03，公共提示 `typed-domain-proposal/0.1.1` 补全既有 `typed-domain-candidate/0.1` 的六个必需且封闭的根字段，明确 `schema_version="typed-domain-candidate/0.1"` 与 `status="unconfirmed"`。这只修正提示枚举遗漏；候选格式、严格检查器、完整原文及有限语言说明不变。缺失/错误判别值或额外根字段仍拒绝，不补默认值或修复历史候选。提示及方法源码字节已变化，须固定新计划；旧计划和固定旧源码哈希的独立评价基线应拒绝当前字节，历史计划/基线不回写。该修正不保证模型遵从格式或领域语义正确。

同日用户明确恢复真实调用。run-06缺根schema_version的拒绝原件保留；窄修后的run-07 S01/S02均返回HTTP200/completed，原始输出未经修补通过typed检查并按原件身份重开审阅。用量分别1477输入+3909输出=5386、1481输入+4757输出=6238 tokens；新增20次累计用4、余16，单次上限40960，旧3次另列，费用未测。S01有3实体、1关系、0约束和7个必需残余；S02有3实体、2关系、0约束和8个必需残余。两份均为unconfirmed，requirement_fidelity=not_checked、instance_conformance=not_run；独立语义验收及回答驱动自动修订尚未完成，不能据此宣布业务可执行或F1/F2完成。

2026-10-02首次0.3离线交付：prepare与execute固定JSON mode，既有提示、typed检查、adapter及审阅接口不变。针对性工程验证核对实际adapter构造的HTTP请求参数、双slot成功后拒第三次、格式删除/改写即使重算hash仍拒绝，以及HTTP400/refusal/incomplete/非法JSON/typed错误原件保留并阻止下一slot。合成响应不计真实语义成功。当时拟S01/S02各一次、每次4096，未释放；该旧准备计划零attempt冻结弃用，不修改原件或执行旧计划。

随后用户明确将调用和输出额度各增加10倍：新增累计20次、每次最多40960输出tokens，旧3次失败仍计入历史。adapter 0.1.2据此接受请求预算1–20、输出上限1–40960，固定socket超时1200秒以适应非流式大输出；app仍0.3，提示与JSON mode不变。2MiB响应信封及256KiB typed候选边界保持，超限仍如实拒绝，不为扩输出额度削弱检查。新首个计划仅两input可执行，reserved_revision_slots=18表示后续需求变化/澄清/明确修复容量，由宿主按实际消耗统一管理，不能在本计划自动循环18次，也不要求耗完。失败保留后先诊断，宿主可在已授权总20次内明确分配恢复；无自动相同请求重试、换模型或备用方式。真实调用由指定宿主执行，工程prepare不冒充实验结果，后续独立评价消费实际可用候选。

0.2增加单输入预算和确定性行表的离线回归，保留既有双输入、AUD01–04和同一候选经审阅/UI读取的工程检查。新提示和方法hash只用于新计划，不回填旧0.1/0.1.1运行。0.2及末尾空行提示窄修经有限工程验收后，宿主已明确放行并执行唯一v2一次；总预算3/3已耗尽。工程通过与来源呈现不证明自动候选合法或忠实。

0.1.1的离线回归使用假凭据、真实标准库HTTPResponse/本机socketpair及公开submit_action，覆盖截断转义回显落盘、短Content-Length、超时21字节前缀、完整配对输入、pending审阅、错request/candidate和合法回答后的继续。没有新增依赖、配置或恢复服务。旧调用的0.1方法hash、失败原件和预算不随修复改写，旧plan在新方法下应拒绝执行；本修复不授权重放或额外真实调用。

定向离线验收：`python -B -I tests/test_language_modeling.py`。合成响应均为工程自测，不计真实样本。覆盖配置、重定向、预算重开/失败/损坏、身份冲突、HTTP/超时/截断、无usage、错模型、非法原件、密钥隔离，以及同一候选经D现有HTTP入口读取。真实供应商配置已由宿主提供；生成次数、最终调用计划、真实结果及独立语义评价须查本轮运行证据，不能由离线测试推出。2026-09-30累计3次POST尝试，预算3/3已耗尽、余0。首次原环境network_error、HTTP状态null、0字节、usage unknown。第二次经显式有界宿主恢复，S01收到HTTP200/gpt-6-luna，但incomplete/max_output_tokens；输入976、输出4096（含推理1763），报告5072 tokens，截断候选被拒绝。第三次使用已审行表/紧凑提示v2，HTTP200、transport received、response completed、返回gpt-6-luna；输入1455、输出3488（含推理1379），报告4943 tokens，输出未达4096上限。其7407字节候选仍因JSON语法错误被拒绝：候选文本末尾报`Expecting ',' delimiter`，typed-inspect退出2。服务端completed不等于JSON合法，本次也没有已证实的token上限截断。独立审核只读取原件中完整可解析的traces子数组：13条full-line引文匹配、0越界，说明引用绑定改善，不证明语义、完整性或候选合法。两次失败候选均保存原件，现有D HTTP入口读取200且candidate_ref/base64一致、存储hash不变；未运行新的完整浏览器验收。已知用量小计10015 tokens加首次未知，金额未测。S02及B正式86/34/5在该时点均not_run；该旧批次无剩余额度，不重试、补JSON或替换失败原件。真实收据与generation_provenance=not_verified分开，审阅仍rejected、语义not_checked、实例not_run，R2/F1/F2未完成。该时点未分配新调用；后续JSON mode与扩额授权见本节2026-10-02记录，不改写上述历史失败。
