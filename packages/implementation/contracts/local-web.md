# 有限本机应用物化与维护合同

`modelspine_implementation.local_web` 消费 generation 的已核验计划与 apps 明确装配的三个运行源码文件，输出新目录。生成包含标准库服务、静态页面、完整 spec/definition、源事实与文件 owner/hash manifest；不导入平台 apps/research，不需原工作区路径或安装第三方依赖。checks 始终使用原有限 checker。目录创建前检查路径、命名冲突、初始数据以及公开成功例的实际 task/view/scope/version 路径；unsupported、冲突和 draft 不创建交付目录。

所有 task/view 及范围来自规格；支持至少一个覆盖全 edit_scope 的四动作视图，不合成多视图事务。范围检查与真实 save 共用同一函数。目标预检检查至少一条正例能在交付时基线数据及已用版本上保存；基线作为生成设置保存，后续正常保存不使 build/restart 的验收基准漂移。build 编译生成的 Python 并重跑公开检查和路径预检；实际 HTTP 行为另行验收。

每次保存解码完整 ProjectModel、核对当前保存 revision、实例 ID、未使用 ProjectModel.version、编辑视图及所有有限义务。只有 satisfied/not_applicable 允许提交，逐项保留不适用原因；violated/unknown/error/不支持/旧版本不写数据。not_applicable 不是非空语义见证。单次请求 2 MiB；存储完整保留每版项目、定义和原报告/hash链，32 MiB 后拒绝而不裁剪。每次重读核验链及报告。

服务只绑定 127.0.0.1，随机进程 token 位于启动 URL fragment；请求须匹配 Host/Origin/凭据。浏览器删去地址栏 fragment，不把 token写入数据。路由固定，无通用文件服务或重定向；拒绝符号链接、junction、hardlink 和相对路径逃逸。会话凭据不是域权限，也不能隔离有同一 OS 文件权限的其他进程。

运行期间持有排他文件锁；线程锁内执行数据版本比较与完整原子保存。竞争请求至多一项提交；旧版本 409。数据先独占写 `.pending`、flush/fsync，再 `os.replace` 和读验。失败保留 pending，后续拒绝。重启正常释放锁后支持；进程硬杀/崩溃遗留锁或 pending 无自动恢复，须显式诊断。仅单数据文件替换具有原子范围，不承诺断电后的目录持久性。

更新只发布到显式新目录：旧目录须停止服务，调用方提供预期 manifest SHA-256；首先核对全部已登记文件，非 data 文件实际 hash 必须匹配。所有 data 必须通过完整历史链及报告重检；缺文件、人工修改生成文件、已登记人工文件变化、未完成写入、链接、命名覆盖均拒绝。未登记人工文件原字节复制并登记 human；空目录因无保留语义明确冲突拒绝，不静默丢失。新路径碰撞也拒绝。

同一 application/project identity、新 spec.version 和旧 manifest hash共同绑定更新。已有数据保留原历史记录；只允许在不修改对象/字段/关系/版本的情况下把最新实例绑定到新定义并重新执行 checker，通过才追加该绑定记录。只改变规格而未改定义时数据历史不加记录。不能更换 storage path 或用新 initial_project替换旧实时数据。迁移、通用合并、自动回滚及崩溃恢复均 unsupported；新规则不满足现存数据时旧目录保持可运行。新目录 build 失败保留 `.incomplete-delivery` 和真实失败结果，不替换旧目录。

manifest 的 data sha256 是交付时内容，后续实际数据以内部链重核；其他 owner/hash是下次更新的预期基准。完整操作与来源责任见 [local-web](../../../docs/local-web.md)。
