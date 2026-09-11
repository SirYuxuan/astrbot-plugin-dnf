# 雨轩查询插件

基于 AstrBot 的查询插件，提供 **DNF 金币比例、油价、蛋价和 EVE 欧服吉他市场** 查询。
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
| EVE 查价 | `/jt 毒蜥级` | `jita` 与 `jt` 完全等价，普通物品查吉他 4-4 |
| EVE 英文查价 | `/jita Gila` | 支持中文、英文和物品 ID |
| PLEX | `/jt PLEX` | PLEX/伊甸币查询全球 PLEX 市场 |

油耗、里程必须大于 0。油价数据源为 iamwawa.cn，蛋价数据源为 quotn.cn。

## 配置

AstrBot WebUI 根据 `_conf_schema.json` 生成配置页面。现有基础配置键保持不变：

- `platform`：主动推送平台名称，默认 `aiocqhttp`。
- `gold`：监控开关、推送群号、检测间隔、波动阈值。
- `oil`：监控开关、推送群号、地区列表、每日检查小时、启动通知。
- `egg`：每日推送开关、推送群号、地区、检测间隔、展示条数。
- `eve`：候选结果数量、ESI/SDE 请求超时、行情缓存、Redis 地址和 User-Agent。

### EVE 初始化与命令

首次使用名称查询前，由 AstrBot 管理员执行：

```text
/jt 数据 更新
```

该操作从 CCP 官方 Tranquility SDE 下载约 100 MB 的 JSONL 压缩包，在后台线程中构建
`data/plugin_data/yuxuandnf/eve/eve.db`。更新过程中不会阻塞其他消息处理。

统一命令入口：

```text
/jt 三钛合金
/jita Tritanium
/jt 34
/jt PLEX
/jt 伊甸币
/jt 搜索 乌鸦
```

PLEX、伊甸币和物品 ID `44992` 使用 Global PLEX Market；其他物品默认查询吉他 4-4。
结果只展示最低卖价、最高收价及两者的算术中间价，不查询数量或计算总价。
输出不显示市场区域。

普通名称查询会同时寻找包含该名称的相关物品，最多显示 `eve.search_result_limit` 个候选，
默认 5 个。例如 `/jt 毒蜥级` 可返回毒蜥级本体及名称中包含“毒蜥级”的其他物品。
默认排除蓝图和涂装；只有查询词明确包含 `蓝图`/`Blueprint` 或 `涂装`/`SKIN` 时，
才会放开对应类别。

管理员可以维护全局别名；别名也可用作固定查询名称：

```text
/jt 别名 添加 小毒蛇 毒蜥级
/jt 别名 删除 小毒蛇
/jt 别名 列表
/jt 别名 添加 月卡 PLEX
/jt 数据 状态
```

行情分页默认缓存在本机 Redis `redis://localhost:6379/0`，缓存前缀为 `yuxuandnf:eve`。
Redis 不可用时会自动退回进程内缓存；将 `eve.redis_url` 留空可关闭 Redis。

**启用前请修改三个功能的推送群号**，默认值为历史配置，不适合所有部署。
监控默认开启；关闭某项 `monitor_enabled` 只停止其后台推送，不影响手动查询。
每日任务使用服务器本地时间，请确认部署环境的时区。
主动群推送仍使用现有的 aiocqhttp 风格客户端，并非任意平台通用推送。

## 目录结构

```text
.
├── main.py                      # AstrBot 命令入口、初始化、卸载
├── metadata.yaml                # 保持原插件标识
├── _conf_schema.json            # 查询与缓存配置
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
│       ├── egg/                 # client.py 数据与格式化；service.py 查询与推送
│       └── eve/                 # SDE 名称库、ESI 行情、Redis 缓存和命令业务
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
- `eve/eve.db`

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
发布前仍需在 AstrBot 中完成命令、管理员权限、名称库更新、Redis 和群推送联调。
