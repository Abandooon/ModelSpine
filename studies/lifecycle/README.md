# 生命周期研究执行入口

当前只有协议和实验身份，没有运行器或数据。权威协议见 [E 协议](../../../research/papers/E/protocol.md)，条件和执行状态见 study.json。

真实 runner/analysis 后续加入本目录，通过平台公开能力调用。运行输出进入独立 artifacts/runs/<study>/<run> 或外部制品库，保留 run manifest。生产包不能依赖本实验目录。每次运行必须固定协议、代码、模型/工具、输入及独立验收版本。
