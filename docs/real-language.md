# 有界真实语言入口（typed-language-run/0.1.1）

`apps/language_modeling.py`将一个原文ModelingRequest经现有typed提示、单一Responses适配器、已有typed检查、A审阅保存交给[本地审阅UI](model-review-ui.md)。这是P1-R2有限入口，不包含自动修复、回答驱动修订、实例生成/检查、提案采纳或应用生成；结构合法不等于原文忠实。生产代码不读取研究样本或独立答案。

协议固定为`POST https://api.openai-proxy.org/v1/responses`、`gpt-6-luna`。供应商[兼容说明](https://doc.closeai-asia.com/tutorial/api/openai.html)支持无状态Responses；[官方参数](https://developers.openai.com/api/reference/python/resources/responses/methods/create)定义input、store、stream、max_output_tokens及响应状态/usage。请求只带model、当前typed提示input、store=false、stream=false、max_output_tokens；不传previous_response_id、工具、温度或假定模型支持的额外推理设置。服务实际支持与模型身份须以调用结果验证，目录可见不等于生成成功。

## 配置与准备

仅标准库，无SDK/自动重试。宿主显式提供公开仓库外的绝对`.env`路径，进程只解析六个精确名称：MODELSPINE_PROVIDER_URL、MODELSPINE_BASE_URL、MODELSPINE_API_KEY、MODELSPINE_MODEL、MODELSPINE_MAX_REQUESTS、MODELSPINE_MAX_OUTPUT_TOKENS。值必须完整，模型和端点必须上述显式值；总请求预算1–3、每次输出上限1–4096（包括服务计入的推理输出）。本入口两请求计划要求总预算至少2。不得打印配置文件或把key放进命令行、提示、工件及公开仓库。TLS保持验证，urllib使用宿主已有系统/环境代理；不关闭TLS、不换域名，全部重定向拒绝。

先用[原文入口](domain-modeling.md)为两份独立原文各准备一个request.json，再执行下列命令（工作目录platform）。不要求人工正确候选。目录父路径须存在，run-dir必须为新绝对路径，重复准备拒绝覆盖。

```text
python -B -I apps/language_modeling.py prepare --env-file "E:/private/.env" --run-dir "E:/runs/explicit-task" --task-id "explicit-task" --request request-1.json --request request-2.json
```

prepare不联网。它保存每份原文的完整UTF-8（包括尾LF）、规范ModelingRequest、现有typed_modeling_prompt的完整文本、无认证头的实际请求JSON。plan.json绑定请求、原文、提示、请求参数、两个顺序slot、方法源码SHA及显式预算，返回plan_sha256。两请求不共享对方原文、响应或参考答案。原始请求文件的JSON排版不作为候选来源，保存的request.json是既有dumps规范编码，原文source.txt保持原字节。

## 明确执行与停止

确认最终计划后，每执行一次命令最多发送一次POST；本轮审核前不得执行：

```text
python -B -I apps/language_modeling.py execute-next --env-file "E:/private/.env" --run-dir "E:/runs/explicit-task" --expected-plan-sha256 "<prepare给出的hash>"
```

执行前再次核对计划hash、方法源码、配置、两个冻结输入的全部hash及各自重新构造的实际请求，包括尚未调用和已经调用的slot。每次先在attempts/001、002排他创建reservation.json并fsync，再联网。该目录是这一任务唯一预算账本，失败和无响应均占用；重启不重置，不允许通过换目录重建同一任务来重置预算。当显式预算为3时，余下1次不由本入口自动使用；预算为2时没有额外名额。跨子批累计预算由宿主明确登记已耗/剩余，本入口不提供跨任务预算服务，不能借新目录抹去旧失败。不得自动循环、修JSON、删除围栏、补默认候选、换模型或换API。

单写者以.run.lock互斥。挂起锁、未完成attempt、receipt/工件损坏都拒绝继续；宿主须先核查是否已经发出或扣费，再另行决定恢复，不能删attempt假装没有消耗。receipt和其hash排他保存；写失败不返回成功，不退回旧缓存。无法持久化联网结果时已有reservation仍保留，调用完成状态为未知。预算不防恶意宿主删除整个账本或伪造所有hash，宿主负责独占目录及原证据保护。

继续前还通过公开read_review重开此前各成功attempt的review-project，由原存储层校验pending/busy、保存hash和动作重放；失败返回review_recovery_failed，不创建下一reservation或POST。装配层核对不可变request_ref与冻结请求、candidate_ref与receipt及candidate.raw，错绑定返回review_binding_conflict。合法answer等动作可以改变review_ref，不要求等于初始收据版本，也不据此声称候选已修订或语义通过。检查发生在各存储锁内的读取时点，不是跨审阅与联网的分布式事务；宿主继续负责运行期间目录及不可变原件不被外部替换。

传输设置120秒socket超时，并在读取块间核对120秒经过时间；不是精确总墙钟截止，单次阻塞读可使总耗时再增加一个socket超时。响应体上限2MiB，超限/网络失败/超时/HTTP非200/截断均保存已收到字节并停止。使用标准库HTTPResponse.read1逐段保留正文，避免填满read(amt)期间超时丢失已到达前缀；EOF时Content-Length尚未满足即truncated_http_body，即使已收正文恰好是完整JSON也不提取候选。正常长度、无Content-Length的正常EOF及完整chunked传输仍可接收。HTTP IncompleteRead保存此前前缀加异常partial，不修正文。任何已有失败、错模型、缺usage、不完整生成或拒绝候选都会停止后续slot；生成预算保留完整分母。

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

0.1.1的离线回归使用假凭据、真实标准库HTTPResponse/本机socketpair及公开submit_action，覆盖截断转义回显落盘、短Content-Length、超时21字节前缀、完整配对输入、pending审阅、错request/candidate和合法回答后的继续。没有新增依赖、配置或恢复服务。旧调用的0.1方法hash、失败原件和预算不随修复改写，旧plan在新方法下应拒绝执行；本修复不授权重放或额外真实调用。

定向离线验收：`python -B -I tests/test_language_modeling.py`。合成响应均为工程自测，不计真实样本。覆盖配置、重定向、预算重开/失败/损坏、身份冲突、HTTP/超时/截断、无usage、错模型、非法原件、密钥隔离，以及同一候选经D现有HTTP入口读取。真实供应商配置已由宿主提供；生成次数、最终调用计划、真实结果及独立语义评价须查本轮运行证据，不能由离线测试推出。2026-09-30累计2次POST尝试：原环境network_error、HTTP状态null、0字节、usage unknown；宿主明确保留旧耗1并分配剩余2的人工恢复子批，进程显式使用既有本机代理。恢复S01收到HTTP200和gpt-6-luna，但incomplete/max_output_tokens；输入976、输出4096（含推理1763），报告合计5072 tokens，金额未核定。截断候选原件经typed-inspect退出2、review保持rejected，D真实HTTP读取200且candidate_ref/base64一致、存储hash不变。S02 not_run；余1未再分派，不再恢复/重试/增上限/补JSON。原失败与新收据分开保存，未知首调用量不并入已知5072当成完整总量。语义未检查、实例未运行，完整F1/F2未完成。
