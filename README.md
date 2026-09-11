# 雨轩基础查询插件

基于 AstrBot 的基础查询插件，仅提供 **DNF 金币比例、油价、蛋价** 三类功能。
保留历史插件标识 `yuxuandnf`，便于已有安装直接升级。

## 功能与命令

| 功能 | 命令示例 | 说明 |
| --- | --- | --- |
| DNF 金币比例 | `/金币比例` | 查询 DD373 金币比例；支持按阈值监控波动 |
| 地区油价 | `/油价 河南` | 查询地区油价；支持每日变动推送 |
| 行驶成本 | `/油价 河南 92 7.5` | 按默认 100 公里计算成本 |
| 指定里程成本 | `/油价 河南 95 8 500` | 油耗单位为升/百公里，里程单位为公里 |
| 地区蛋价 | `/蛋价 平舆` | 查询蛋价；支持每日群推送 |
| 历史蛋价 | `/蛋价 平舆 20260911` | 日期格式为 YYYYMMDD |

油耗、里程必须大于 0。油价数据源为 iamwawa.cn，蛋价数据源为 quotn.cn。

## 配置

AstrBot WebUI 根据 `_conf_schema.json` 生成配置页面。现有基础配置键保持不变：

- `platform`：主动推送平台名称，默认 `aiocqhttp`。
- `gold`：监控开关、推送群号、检测间隔、波动阈值。
- `oil`：监控开关、推送群号、地区列表、每日检查小时、启动通知。
- `egg`：每日推送开关、推送群号、地区、检测间隔、展示条数。

**启用前请修改三个功能的推送群号**，默认值为历史配置，不适合所有部署。
监控默认开启；关闭某项 `monitor_enabled` 只停止其后台推送，不影响手动查询。
每日任务使用服务器本地时间，请确认部署环境的时区。
主动群推送仍使用现有的 aiocqhttp 风格客户端，并非任意平台通用推送。

## 目录结构

```text
.
├── main.py                      # AstrBot 入口：三个命令、初始化、卸载
├── metadata.yaml                # 保持原插件标识
├── _conf_schema.json            # 三类基础功能的配置
├── plugin/
│   ├── application.py           # 集中装配功能与共享依赖
│   ├── core/
│   │   ├── config.py            # 默认配置、合并和读取
│   │   ├── feature.py           # 监控功能的共享依赖
│   │   ├── notifications.py     # 群通知接口
│   │   ├── runtime.py           # 统一后台任务生命周期
│   │   └── storage.py           # 原子 JSON 存储和旧状态迁移
│   ├── adapters/astrbot/
│   │   ├── commands.py          # 事件读取、结果包装、异常回复
│   │   └── notifications.py     # AstrBot 平台群消息适配
│   └── features/
│       ├── gold/                # client.py 数据查询；service.py 查询与监控
│       ├── oil/                 # client.py 数据与格式化；service.py 查询与监控
│       └── egg/                 # client.py 数据与格式化；service.py 查询与推送
├── tests/                       # 离线测试，无需真实平台或外部 API
├── docs/architecture.md         # 分层约定、扩展方式、已知限制
├── pyproject.toml              # Python 依赖和代码检查配置
├── uv.lock                      # 开发环境依赖锁定
└── requirements.txt             # AstrBot 插件运行依赖
```

## 运行时状态与升级

运行环境需要 Python 3.10+，以及提供 `StarTools.get_data_dir` 的 AstrBot 版本。
插件数据放在 AstrBot 的 `data/plugin_data/yuxuandnf/`，不再向代码目录写入状态：

- `last_avg_ratio.json`
- `last_sent_avg_ratio.json`
- `last_oil_data.json`
- `last_egg_sent_date.json`

当新数据目录没有对应文件时，首次加载会读取插件根目录中的旧状态并写入新目录。
旧文件不会删除；新目录已有状态时以新状态为准。升级前建议备份根目录中的旧状态文件。
迁移需要这些文件仍位于安装后的插件根目录；若更新工具清空目录，请从备份恢复后再启动。

图片与音乐生成的实现、命令和配置项已删除。旧配置中残留的未知字段不会被加载；
本次代码更新不会修改 AstrBot 外部已保存的配置文件，历史密钥请在部署端自行删除。
旧内部包 `dnf_plugin` 已移除，不保留内部导入兼容层。

## 开发验证

```bash
uv sync --group dev
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
```

测试使用模拟数据与平台替身，不会真实调用行情接口或发送群消息。
发布前仍需在 AstrBot 中完成三个命令、启动推送、配置开关及卸载任务的联调。
