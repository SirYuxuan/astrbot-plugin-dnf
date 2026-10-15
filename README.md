# 烟雨机器人插件

基于 AstrBot 的查询插件，提供 **DNF 金币比例、油价、蛋价和 EVE** 查询。
保留历史插件标识 `yuxuandnf`，便于已有安装直接升级。

## 功能与命令

以下指令使用 AstrBot 配置的唤醒前缀（示例为 `/`），并可在“插件 → 管理行为 → 指令”中启停和管理。

| 功能 | 命令示例 | 说明 |
| --- | --- | --- |
| 插件帮助 | `/help` | 显示烟雨机器人插件指令帮助 |
| DNF 金币比例 | `/金币比例` | 查询 DD373 金币比例；支持按阈值监控波动 |
| 地区油价 | `/油价 河南` | 查询地区油价；支持每日变动推送 |
| 行驶成本 | `/油价 河南 92 7.5` | 按默认 100 公里计算成本 |
| 指定里程成本 | `/油价 河南 95 8 500` | 油耗单位为升/百公里，里程单位为公里 |
| 地区蛋价 | `/蛋价 平舆` | 查询蛋价；支持每日群推送 |
| 历史蛋价 | `/蛋价 平舆 20260911` | 日期格式为 YYYYMMDD |
| EVE 角色收益 | `/rat` | 查询发送者绑定角色的 RAT 收益 |
| RAT 每日订阅 | `/subrat` | 切换订阅；每天北京时间 23:50 推送到发送者 QQ 私聊，再发一次取消 |
| EVE 角色信息 | `/info` | 查询发送者绑定的 EVE 角色信息 |
| EVE 配置导入 | `/fitt` | 仅 QQ 私聊，依次发送角色名、完整 EFT 配置；`/cancel` 或“取消”退出 |
| EVE 查价 | `/jt 毒蜥级` | `jita` 与 `jt` 完全等价，普通物品查吉他 4-4 |
| EVE 英文查价 | `/jita Gila` | 支持中文、英文和物品 ID |
| EVE 名称翻译 | `/tr raven` | 自动识别中英文；重名时列出候选与 ID，可用 `kind=type` 筛选 |
| EVE 导航 | `/nav ALL 吉他` | 为发送者 QQ 绑定的全部授权角色设置航点；指定角色可用 `/nav "角色名" 吉他` |
| PLEX | `/jt PLEX` | PLEX/伊甸币查询全球 PLEX 市场 |
| EVE 合计查价 | `/col 中级水晶` | 查询一个或多个匹配物品，并汇总最低卖价；也支持末尾数量 |
| KB 战绩 | `/kb Yuxan Axiom` | 按完整角色名查询 zKillboard 公开战绩 |
| KB 最近击杀/损失 | `/kbk 角色ID`、`/kbl 角色ID` | 获取角色最近一次击杀或损失，生成详细战报图片 |
| 军团、联盟 KB | `/kb 军团 The Ninth Person`、`/kb 联盟 Brotherhood of Spacers` | 按完整名称查询军团或联盟统计 |
| 军团 KB 订阅 | `/subkb` | 在群聊中订阅或取消军团击杀、损失私聊通知 |
| 联盟 KB 订阅 | `/suballkb` | 在 KOOK 频道订阅或取消联盟击杀、损失通知 |
| EVE 计时 | `/timer 2天2小时5分` | 计算指定时长后的 EVE 时间和北京时间 |
| EVE 状态 | `/status` | 查询 Tranquility 服务器状态和在线人数 |
| 舰船资料 | `/ship 乌鸦级` | 查询舰船槽位、挂点与角色/技能加成，返回图片卡片 |
| 舰船训练 | `/train 乌鸦级` | 查询发送者绑定角色驾驶舰船所需的立即训练时间 |

油耗、里程必须大于 0。油价数据源为 iamwawa.cn，蛋价数据源为 quotn.cn。

### 私聊配置导入

私聊发送 `/fitt` → 机器人提示“请输入角色名” → 发送完整角色名 →
机器人提示“请发送配置” → 发送完整 EFT 文本 → 返回配置导入成功或失败。
接口使用消息发送者的 QQ，不允许指定他人 QQ。配置可以保留换行，也支持 Markdown 代码块。
每步 5 分钟无操作后过期；发送 `/cancel` 或“取消”退出，重新发送 `/fitt` 从头开始。
发送其他 `/` 指令会结束当前导入并正常执行该指令。插件重载或机器人重启后需重新开始。
收到有效配置即结束输入会话，不自动重试写入请求；网络异常时先到游戏内确认结果，避免重复导入。

## 配置

AstrBot WebUI 根据 `_conf_schema.json` 生成配置页面。现有基础配置键保持不变：

- `platform`：主动推送平台名称，默认 `aiocqhttp`。
- `gold`：监控开关、推送群号、检测间隔、波动阈值。
- `oil`：监控开关、推送群号、地区列表、每日检查小时。
- `egg`：每日推送开关、推送群号、地区、检测间隔、展示条数。
- `rat`：查询接口、超时和每日私聊推送开关。
- `eve_dt`：EVE 每日 DT 提醒开关、推送群号、开服检测间隔和 ESI 状态地址。
- `kb`：zKillboard 请求超时、缓存时间、接口地址和 User-Agent。
- `kb_watch`：军团/联盟 ID、默认订阅 QQ 列表和 zKillboard R2Z2 实时流配置。
- `translate`：EVE 名称翻译接口地址和请求超时。
- `navigation`：EVE 航点接口地址和请求超时。
- `ship`：舰船资料、图标接口和请求超时。
- `eve`：候选结果数量、Fuzzwork/SDE/Adam4EVE 请求超时、行情缓存、Redis 地址和 User-Agent。

KB 查询支持角色、军团和联盟；未指定类型时仍按角色名查询。查询使用紧凑文本输出，包含威胁度、团战率、击杀及损失数量与金额、单杀、
ISK/舰船击损比和 zKillboard 详情链接。角色名通过 CCP ESI 精确解析，查询结果默认缓存
10 分钟；角色名包含空格时直接完整输入即可。

`/ship 乌鸦级` 使用 OOFO 舰船资料接口查询中英文名、描述、槽位、挂点及加成，再根据
返回的 `typeId` 获取实际舰船 PNG。图片会嵌入 HTML 后交给 AstrBot 截图并发送。
本地预览可运行 `uv run python scripts/ship_preview.py`，打开
`http://127.0.0.1:8766/eve-ship-card-preview.html`，输入舰船名称即可实时查询。

`/nav` 使用消息发送者的 QQ 绑定信息；`ALL`（不区分大小写）会为所有授权角色设置航点。
角色名或星系名含空格时使用英文引号，例如 `/nav "Yuxan Axiom" "New Caldari"`。
目的地可用星系中文名、英文名或 ID。角色须已授权 `esi-ui.write_waypoint.v1`，游戏客户端须在线；
回复会逐角色列出成功或失败原因。

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

PLEX、伊甸币和物品 ID `44992` 使用 Global PLEX Market，并默认展示 500 个的总价；
其他物品默认查询吉他 4-4。结果只展示最低卖价、最高收价及两者的算术中间价。
输出不显示市场区域或图标；中文查询只显示中文物品名，英文查询只显示英文物品名。

普通名称查询会直接查询名称模糊匹配结果的价格，最多显示 `eve.search_result_limit` 个物品，
默认 5 个，无需再输入物品 ID。例如 `/jt 毒蜥级` 可返回毒蜥级本体及名称中包含
“毒蜥级”的其他物品及其价格。
如果查询词与某个官方中文名或英文名完全一致，则只查询该物品，不再扩展相似名称。
`/jt`、`/jita` 只回复文字价格，不请求历史行情，也不发送走势图图片。
当前行情使用 Fuzzwork：普通物品查询吉他 4-4 空间站，PLEX 查询全局市场；多个
匹配项只发起一次批量查价。运行时不请求 CCP ESI。
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

行情分页和历史结果默认缓存在本机 Redis `redis://localhost:6379/0`，缓存前缀为
`yuxuandnf:eve`。Adam4EVE 历史默认缓存 6 小时，Redis 默认保留 12 小时。
Redis 不可用时会自动退回进程内缓存；将 `eve.redis_url` 留空可关闭 Redis。

本地测试查价消息效果（使用 CCP SDE 名称库和 Fuzzwork 真实行情）：

```bash
uv run python scripts/eve_preview.py
```

浏览器会自动打开 `http://127.0.0.1:8765`，可直接输入 `/jt 毒蜥` 等命令。首次运行会
下载并构建名称库；后续复用 `.eve-preview/eve.db`。如果本机 Redis 不可用会自动回退到
进程内缓存，也可使用 `--redis-url ''` 明确禁用 Redis。

**启用前请修改三个功能的推送群号**，默认值为历史配置，不适合所有部署。
监控默认开启；关闭某项 `monitor_enabled` 只停止其后台推送，不影响手动查询。
每日任务使用服务器本地时间，请确认部署环境的时区。
主动群推送仍使用现有的 aiocqhttp 风格客户端，并非任意平台通用推送。

`/subrat` 可在 QQ 群聊或私聊中使用，按发送者 QQ 保存订阅状态；每天北京时间 23:50
调用与 `/rat` 相同的接口，并将报告发给订阅者私聊。再次发送即可取消。订阅者需先绑定
EVE 角色、添加机器人好友并允许私聊。订阅状态与各用户的最近推送日期保存在
`rat_subscriptions.json`；插件启动或重载时不立即发送报告。

EVE DT 监控会在北京时间每天 18:55 向 `eve_dt.notify_group_id` 发送
“5分钟后游戏DT。”，19:00 起每 30 秒查询一次 ESI 状态。检测到当天 DT 后服务器已启动、
存在在线玩家且不处于 VIP 模式时，只发送一次“游戏已经开服！！！”。通知状态保存在
`eve_dt_state.json`，DT 期间重启插件后可继续检测。

军团 KB 监控使用 zKillboard R2Z2 实时流，首次启动从最新序号开始，不回放历史击杀。
群成员可用 `/subkb` 切换订阅，订阅列表保存在 `kb_watch_state.json`，支持多个 QQ。
通知会发往订阅者私聊，因此订阅者需先添加机器人好友并允许平台私聊。
QQ 私聊推送为战报图片，包含 UTC+8 时间、蓝色加粗星系、参与者舰船与武器、伤害和掉落/损毁装备。
现有军团订阅仍只推送 QQ 私聊；在 KOOK 目标频道执行 `/suballkb` 后，联盟 `99007887`
的全部击杀和损失会单独推送至该频道，再次执行即可取消，且支持订阅多个 KOOK 频道。
KOOK 通知使用窄版紧凑原生卡片，包含小尺寸舰船图、最后一击与被击杀角色头像、双方军团及
联盟徽标、身份信息、损失价值和 zKillboard 战报链接；卡片发送失败时自动降级为文字。
插件加载或重载时不发送联盟 KB 测试卡片；已订阅频道只接收实时击杀和损失通知。

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
│       └── eve/                 # SDE 名称库、Fuzzwork 行情、Redis 缓存和命令业务
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
