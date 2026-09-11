# EVE 欧服查价功能设计与首版实现

调研日期：2026-09-11。仅考虑 Tranquility；“伊甸币”按 PLEX 理解，不是 ISK 本身。

## 推荐决策

- 名称来源：CCP 官方 SDE，导入本地 SQLite，保留英文与可用中文名称。
- 名称匹配：本地名称库 + 管理员维护别名；模糊命中有歧义时返回候选，不猜测交易物品。
- 行情来源：首版直接使用 CCP 官方 ESI 公共市场订单接口。
- 普通物品默认市场：吉他 4-4 NPC 空间站；不是整个吉他星系或伏尔戈星域的最低价。
- PLEX：使用 Global PLEX Market 对应区域，不套用普通物品的吉他空间站筛选。
- 固定查询：使用管理员维护的别名绑定 type_id。
- 首版只实现查询、管理员别名维护和名称库同步，不做监控推送、角色登录、结构市场、历史曲线。

## 实际查询流程

命令文本 → 解析 ID/名称/别名 → 本地解析 type_id → 确定市场 → 获取缓存或 ESI 订单 → 计算报价 → 格式化回复。

解析优先级建议：

1. 显式数字 type_id（必须验证是否为可交易物品）。
2. 精确别名。
3. 中英文官方名精确命中。
4. 前缀/子串检索。
5. 相似度排序候选，用于拼写错误和相近名称。

名称归一化使用 Unicode NFKC、casefold、空白折叠；不要删去 II、型号数字等有区分意义的信息。
只有精确且唯一匹配直接查价；其他匹配给出最多 5 个“中英文名 + type_id”候选，让用户用 ID 查询。
首版不做拼音、繁简自动转换、跨消息候选会话。

普通查询默认过滤名称含 `蓝图`/`Blueprint` 和 `涂装`/`SKIN` 的候选；查询词明确包含
对应关键词时才放开。候选上限由 `eve.search_result_limit` 配置，默认 5、运行时限制为 1-20。

## 本地数据

建议 `data/plugin_data/yuxuandnf/eve/eve.db`，由 EVE 功能模块自行管理。

- `types`：type_id、group_id、market_group_id、published。
- `type_names`：type_id、language、name、normalized_name。
- `aliases`：normalized_alias 唯一、展示别名、type_id、创建者、时间。
- `metadata`：SDE 版本、同步时间、schema 版本。

查询搜索范围默认为已发布且有市场组的物品。允许保存完整类型库，用于解释“存在但不可在市场交易”。
未知 ID 不能直接写入别名；别名不允许与其他物品的官方名或已有别名冲突。
首版采用全局管理员别名，不开放普通群成员修改，避免污染所有群的查询结果。

名称库通过管理员命令显式同步；下载和导入在后台执行，不阻塞消息事件循环。
在事务中更新，失败继续使用旧库；别名必须在升级时保留。
首次同步前允许 ID 查询与明确提示“名称库尚未初始化”。静态数据库不提交到源码仓库。

## 行情与口径

普通物品：

```http
GET https://esi.evetech.net/markets/10000002/orders?order_type=all&type_id=<TYPE_ID>
```

使用兼容日期机制固定经过测试的行为；示意 URL 的具体尾斜杠、参数与响应以实现时的官方 OpenAPI 为准。
读取所有分页后，过滤 `location_id == 60003760`，分别聚合买单与卖单：

- 卖单最低价：从已有卖单买入的参考单价。
- 买单最高价：卖给已有买单的参考单价。
- 中间价为最低卖价与最高收价的算术平均值；任一侧无报价时中间价也显示暂无报价。
- 输出不显示市场区域、来源、挂单量、价差、数量和数据时间。

首版严格使用该空间站挂出的订单，不计算其他地点买单的跨范围可成交性。
订单最小成交量、手续费、税费、技能及实际成交前的价格变化会影响最终交易，输出为市场报价而非保证成交。
无买单/卖单分别显示暂无报价，不能显示 0 或自动换市场。

PLEX 使用 type_id `44992`、region_id `19000001`，不筛选吉他 station_id。
本次实际访问旧兼容路径 `/latest/markets/19000001/orders/?order_type=all&type_id=44992` 返回 HTTP 200，
`X-Pages: 2`，第一页 1000 条记录；这是接口连通性验证，不是完整实时价格计算。

不要把 ESI 的 `/markets/prices` 平均/调整价格当成吉他买一卖一。

## 固定查询与别名

- 别名回答“这个词对应什么物品”，例如“月卡” → `44992`。
- PLEX/伊甸币自动使用 Global PLEX Market，其他物品使用吉他 4-4。
- 固定查询直接通过别名实现，不动态注册命令，也不保存数量。

建议命令：

```text
/jt 三钛合金
/jita Tritanium
/jt 34
/jt 搜索 乌鸦
/jt 别名 添加 月卡 PLEX
/jt 别名 删除 伊甸币
/jt 别名 列表
/jt 别名 添加 月卡 44992
/jt 数据 更新
/jt 数据 状态
```

写入别名和触发数据更新必须检查 AstrBot 管理员权限。命令解析应支持带空格的英文物品名。

## ESI 与 Fuzzwork 的选择

ESI 是官方原始订单源，不引入第三方聚合依赖；代价是自行分页、筛选、聚合。
Fuzzwork 提供按 station/region 批量 type IDs 的聚合接口，开发快，适合后续批量估价，但有独立的同步与聚合口径。
首版选 ESI，不同时实现双行情源；也不静默切换 Fuzzwork，以免市场范围、更新时间和口径不同却显示相同标签。
后续若增加 Fuzzwork，必须保留来源、市场、数据时间及降级标识。

## 缓存和健壮性

- 按“服务器 + 市场 + type_id + 分页”使用 Redis 共享缓存；Redis 失败时降级到内存缓存。
- 尊重 Expires/ETag/Last-Modified，并使用条件请求复用未变化的数据。
- 相同标的并发查询合并为一个请求；对跨物品请求设并发上限。
- 按 X-Pages 抓取完整订单集；部分分页失败时不能把剩余部分当完整报价。
- 检查各页 Last-Modified，发现跨刷新周期的不一致则有限重试。
- 设置可识别 User-Agent 和固定测试过的 X-Compatibility-Date；不在运行时每天自动改兼容日期。
- 限流/服务错误采用有限重试和退避，遵守响应头，不硬编码永久有效的速率配额。
- 允许短时间内降级展示旧缓存，但必须明确“缓存报价”和原始时间；超过最大陈旧期限就报查询失败。
- 数据库操作和同步 HTTP 请求不得直接阻塞 AstrBot 事件循环。

## 对当前架构的落点

`plugin/features/eve/` 建议包含：

- `service.py`：查询流程、别名管理、对外返回文本。
- `catalog.py`：名称库、名称解析和别名持久化。
- `sde.py`：版本检查、下载、解析、原子导入。
- `client.py`：ESI 请求、分页、缓存、订单聚合。

先使用上述四个实质模块；不抽象通用金融行情框架，不提前建立大量 Protocol 或 provider 子目录。
在 PluginApplication 装配 EveFeature，main.py 声明命令；无定时推送则不加入 FeatureRuntime。
同步任务如需持续到命令结束后，必须归功能拥有并在插件卸载时统一回收，不留下无主任务。

## 分阶段验收

1. 名称库：中英文查名、ID 校验、模糊候选、别名冲突与持久化、更新不丢别名。
2. 行情：普通物品吉他报价、PLEX 全球市场、完整分页、无行情、缓存及限流测试。
3. 交互：管理员权限、别名配置、清晰错误提示与真实 AstrBot 联调。

## 核验资料

以下为本次直接读取的第一方文档/接口；没有依赖第三方攻略的字段说明：

- CCP ESI 概览与兼容日期：https://developers.eveonline.com/docs/services/esi/overview/
- CCP ESI 缓存与请求实践：https://developers.eveonline.com/docs/services/esi/best-practices/
- CCP PLEX 类型信息：https://esi.evetech.net/latest/universe/types/44992/?language=en
- CCP PLEX 市场区域：https://esi.evetech.net/latest/universe/regions/19000001/
- CCP PLEX 订单连通性：https://esi.evetech.net/latest/markets/19000001/orders/?order_type=all&type_id=44992
- CCP 吉他空间站：https://esi.evetech.net/latest/universe/stations/60003760/
- Fuzzwork 自身聚合接口说明：https://market.fuzzwork.co.uk/api/

SDE 的当前格式、中文覆盖情况以同目录名称数据调研记录为补充；不要假设所有类型都有中文名。
