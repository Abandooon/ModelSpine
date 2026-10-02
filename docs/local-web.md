# 本机 ProjectModel 应用生成与更新

该有限目标交付独立的 Python 标准库服务与静态应用页，实际编辑、服务端检查、显式保存和读取 ProjectModel。它是明确选择的确定性模板；没有模型调用、第三方运行依赖、域 Operation/Policy、远程集成或后台业务。手写工程输入只证明工程路径，不能证明 F1/F2/F3/F4 真实主链完成。

先按 [application-spec](application-spec.md) 在一个当前审阅工程中保存/明确确认规格；`generation_ready` 是必要条件。本目标还要求至少一个完整范围视图绑定四动作，且至少一条公开成功例可以按相同范围和版本规则保存。分散视图不能完成该路径时明确 unsupported，不自动合成事务。若有初始数据，公开成功例须使用尚未保存的 ProjectModel.version。规格的正例 checker结果及目标路径预检均不替代真实 HTTP 业务验收。

从平台根运行，所有目录参数显式指定绝对路径；OUTPUT_ROOT 和审阅目录必须已存在，RELEASE_NAME 必须是尚不存在且位于 OUTPUT_ROOT 内的目录。

```text
python -B -I apps/local_web.py load-spec --project-dir ABS_REVIEW
python -B -I apps/local_web.py generate --project-dir ABS_REVIEW --output-root ABS_OUTPUT_ROOT --name RELEASE_NAME
```

load-spec 通过 A 的实际存储入口重放当前 review、来源/定义/候选/spec 绑定、专用内容确认和公开验收，并检测读取中变化；不会使用缓存 ready。生成前再次读取。draft、伪造/旧引用、缺配置与必需残余均拒绝。具体目录支持冲突由 materializer在创建前检查。公开入口以生成后返回的 build.exit_code、stdout/stderr 判断结果，不能凭目录或首页 200 认定交付。

交付目录可以移走，直接使用 Python 3.10+：

```text
python -B -I run.py build
python -B -I run.py serve
```

启动打印一次带随机会话凭据的 loopback URL，在本地浏览器打开。页面按规格展示 views 和 task 按钮，完整 JSON 原文交给服务端解析，Int64 不经过 JavaScript Number。check 展示逐项义务；只有显式 save 写入。版本冲突保留当前输入，用户显式 load 重新读取。无初始实例时编辑框为空，操作人输入明确 ProjectModel，不补默认业务数据。

Ctrl+C 正常停止并释放锁。自动化本机宿主可显式加 `--stop-on-stdin-eof` 并保持 stdin 管道，关闭管道时正常停止；它不增加 HTTP 管理动作。每次启动重新核对 generated 文件及数据，读/存都重检数据历史。所有保存版本保留，达到 32 MiB 只拒绝后续保存；请求上限 2 MiB。旧数据 revision 返回409；业务违反/unknown/error返回422；有链接/路径冲突、无法保存或不支持时如实失败。

更新先停止旧服务，准备同一项目的新明确规格与确认，提供旧 manifest 文件真实 SHA-256：

```text
python -B -I apps/local_web.py update --project-dir ABS_REVIEW --output-root ABS_OUTPUT_ROOT --name NEW_RELEASE --old-root ABS_OLD_RELEASE --expected-manifest-hash SHA256
```

所有旧 manifest 文件先检查。修改生成文件、遗漏文件、已登记人工文件 hash变动或冲突均拒绝；未登记人工文件原字节带入新目录并登记 owner=human，无法保留的空目录明确拒绝。data 通过实际历史链重核。只支持存储位置不变、现存数据可完整重绑新定义并通过原 checker 的更新；初始数据替换与数据迁移不支持。旧目录不被覆盖，成功生成后由用户明确启动新目录。运行数据在两份目录间不会自动同步，不得把双目录当并发数据库。

更新失败不会改写旧数据或代码。新目录 build 失败保留 `.incomplete-delivery`、stdout/stderr；该目录不能 serve。正常已保存数据可重启读取，但遗留锁/pending不自动清除，不提供自动回滚、崩溃恢复或数据迁移。文件原子保存范围与所有权细节见 [implementation 合同](../packages/implementation/contracts/local-web.md)。

apps 显式装配三个固定来源：原 `apps/domain_checks.py`、`protocols/__init__.py` 和 `protocols/domain_language.py`，保持源码原字节；runtime manifest记录源相对路径、实际 module/capability版本、当前 Git HEAD 和逐文件 SHA-256。HEAD不是未提交字节的证明。其他 runtime/template文件由本目标生成并记录 hash。制品附原来源声明，平台整体仍未声明许可证，不把旧来源许可扩大到所有新代码；不复制平台、BESSER或研究材料。

包职责见 [generation 合同](../packages/generation/contracts/local-web.md)；生产包只导入 protocols/generation标准接口，apps 拥有固定检查器装配。无依赖探测器、安装器、其他后端或失败后的自动降级。
