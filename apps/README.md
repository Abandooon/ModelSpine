# 平台应用

用于平台工作台与 CLI 的真实应用入口。用户生成的软件项目放在独立仓库/工作区，以项目清单关联；实验实例由 studies 管理。

[offline.py](offline.py) 串联四包和订单设计模型，运行 `python platform/apps/offline.py`；`--threshold -1` 明确拒绝并退出 2。bootstrap.py 仅连接本工作区四包的 src，既不安装旧依赖也不加载外部工作树。CLI 不生成应用仓库，不执行业务批准，不持久化。

[平台入口](../README.md)
