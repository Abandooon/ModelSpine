# 平台代码边界与当前状态

已完成九模块 S1 合同；四包提供有限离线模型变更切片，尚无完整无代码平台。packages 按能力组织，初期同仓独立包。实际状态见各 module.json；总导航和论文关系见 [工作区](../README.md)。

从工作区根运行 `python platform/apps/offline.py`，执行有限构造→预览→检查→决定→提交→证据适用性；`python platform/run_tests.py` 运行行为验收。仅标准库，无安装步骤。本机 Python 路径由 workspace.local.json 指定。[订单模型与试点假设](domain-packs/order-approval/README.md)；[实际运行证据](../artifacts/audits/modelspine/2026-09-21/README.md)。

- [protocols 接口草案](packages/protocols/contracts/v0.1/README.md)
- [适配器](adapters/README.md)
- [领域包](domain-packs/README.md)
- [平台应用](apps/README.md)
- [生命周期研究入口](studies/lifecycle/README.md)

将来公开此目录时，单独确定许可证与发布清单，不包含上层研究稿件、原始审稿材料、参与者数据或本机配置。当前未初始化独立 Git 仓库。


目标平台名称为 **ModelSpine Studio**。已有 P0 源码保存在 [来源快照](../artifacts/sources/p0/2026-09-20/README.md)；该目录用于审查与提取，不作为本平台运行依赖。提取成果按 packages/adapters/domain-packs 分层落地并单独验证。
