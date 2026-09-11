# EVE Online 欧服 Jita 4-4 历史价格接口调查

> 调查日期：2026-09-11
> 目标：在**不自行长期采样**的前提下，获得 Tranquility（欧服）Jita IV - Moon 4 - Caldari Navy Assembly Plant（station `60003760`）至少 30 天的价格时间序列。
> 本文把三类常被混称为“历史价格”的数据严格分开：
>
> 1. **区域成交历史**：CCP ESI 按 region 提供的日成交 `average/highest/lowest/volume/order_count`；The Forge 是 `10000002`，它不等于 Jita 4-4。
> 2. **单站订单快照历史**：过去各时点在 station `60003760` 可见的最高收单、最低卖单或完整 order book；这才适合画“Jita 4-4 买/卖价走势”。
> 3. **区间聚合值**：例如 5 日/30 日中位数，只有一个汇总数，不能还原逐日曲线。

## 结论摘要

**存在第三方数据源，但没有发现一个同时具备“轻量 JSON、一次请求、官方稳定 SLA、精确 Jita 4-4、30 天逐日最高收价/最低卖价”全部条件的接口。**

可用候选按推荐顺序为：

1. **Adam4EVE `tracker` API（推荐用于第一版）**：可按 `locationID=60003760` 和日期查询单站数据，返回当天推断成交的 buy/sell `low/avg/high`。它是真正的单站历史，但属于基于每 10 分钟订单簿变化推断的成交，不是每日 best bid / best ask 快照；30 天需要约 30 次请求，受 1 次/5 秒限制。
2. **Adam4EVE `MarketPricesStationHistory` 静态 CSV（数据语义最符合订单价走势图）**：明确包含 `location_id=60003760` 的逐日 `buy_price_low/avg/high` 与 `sell_price_low/avg/high`，来自 ESI order book；无需认证，历史目录从 2022 年延续到当前。缺点是按周、按全部枢纽物品打包，单个近期 hub CSV 实测约 27.3 MB，在线查询一个物品需下载并筛选约 5 个周文件。
3. **Adam4EVE `hub_type_history.php` 页面（工程上最快但非正式 API）**：一个 GET 可返回指定物品和站点的长周期数据，价格数组直接嵌在 HTML 的 Dygraph 初始化代码中；实测单页约 140–165 KB、约 2–4 秒。它免认证且避免 30 次 tracker 请求，但 HTML/JavaScript 格式没有版本化接口合约，随时可能变化，只适合作为带降级机制的抓取源。
4. **CCP ESI / EVE Tycoon / Goonmetrics / EVE Market Browser 的 The Forge 历史**：接入最简单、数据最稳定，但均是**区域成交历史**，不能标成 Jita 4-4 历史。
5. **Janice**：可给 Jita 市场的 5/30 日中位数，但没有日期序列，不能画 30 日走势。

若产品文案必须写“Jita 4-4 30 日价格走势”，建议第一版采用 **Adam4EVE tracker 的每日 buy/sell 平均推断成交价**，并在图例或脚注中明确“基于订单簿变化推断”。若必须展示“每天最高收单/最低卖单”，则使用 Adam4EVE 的 station-history CSV，并在服务端按周下载、解析后做普通 HTTP/Redis 缓存；缓存第三方已采集数据不属于本地自行采样。

## 可用性对照表

| 来源 | 精确到 `60003760` | 至少 30 天序列 | 数据类别 | 认证 | 已知限流/更新 | 可集成性 |
|---|---:|---:|---|---|---|---|
| Adam4EVE `tracker` | 是 | 是，按日逐次请求 | 单站推断成交 | 无；必须带可联系的 User-Agent | 1 请求/5 秒；订单簿每 10 分钟抓取 | **可用，首选轻量方案** |
| Adam4EVE station CSV | 是 | 是；2022 至今 | 单站订单最优价的日 low/avg/high | 无 | 每日生成、按周文件；近期 hub 文件约 27.3 MB | **可用，语义最佳但流量大** |
| Adam4EVE `market_price_history` | 否 | 是 | 区域订单快照聚合 | 无 | 1 请求/5 秒；最大约一年窗口 | 可用但不是单站 |
| Janice v2 | 市场配置指向 Jita | **否** | 5/30 日中位数汇总 | `X-ApiKey`，需 Discord 申请 | 文档未公开额度 | 不满足走势图 |
| Fuzzwork | 当前价可精确到站 | **否** | 当前订单聚合 | 无 | 未公布硬限额 | 不满足历史 |
| EVE Tycoon | 当前 stats 可到站；history 不可 | history 是区域级 | ESI 区域成交历史镜像 | 无 | 当前约 5 分钟；历史每日；要求遵守 `Expires` | 区域图可用 |
| Goonmetrics | 当前价可到站；history 不可 | history 是最近 30 天区域级 | 当前站点价 + 区域成交历史 | 无 | 文档未声明 | 区域图可用，XML |
| EVE Marketer | 仅 region/system 当前统计 | **否** | 当前订单聚合 | 无 | 当前实测 503 | 不可依赖 |
| EVE Workbench | 未找到公开可用接口 | 未证实 | UI/内部服务不明 | 不明 | 不明 | 不建议集成 |
| EVE Market Browser | 当前订单可显示站点；history 为区域 | 否（单站） | ESI 区域成交历史 | 网站无登录；无公开 API 合约 | 内部缓存 | 不建议调用内部接口 |
| EveKit（补充） | 历史 order book 内含 location | 曾经可以 | 5 分钟区域订单簿快照，可筛站点 | 无 | 服务于 2019 年宣布关闭 | 不能作为线上依赖 |

## 基准：CCP ESI 为什么不能直接给单站历史

CCP 官方 ESI 是第三方开发的权威 API；市场历史路由的维度是 `region_id + type_id`，即 `GET /markets/{region_id}/history/`，返回区域日成交统计。当前订单路由虽然返回每个订单的 `location_id`，可筛出 Jita 4-4，但只表示当前订单簿，不接受历史日期。因此，第三方若能提供单站历史，必然来自它自己长期保存的历史订单簿，而不是另一条 CCP 单站历史路由。

证据：

- [CCP ESI 官方概览](https://developers.eveonline.com/docs/services/esi/overview/)说明 ESI 是官方第三方 REST API。
- [CCP API Explorer](https://developers.eveonline.com/api-explorer)中的 market history 路由以 `region_id` 为路径参数。
- 可直接验证的 ESI 请求：[`/markets/10000002/history/?type_id=34`](https://esi.evetech.net/latest/markets/10000002/history/?type_id=34&datasource=tranquility)。结果只有日期和区域成交统计字段，没有 station/location 字段。
- EVE Market Browser 的开源实现同样调用 `fmt.Sprintf("/markets/%d/history?type_id=%d", regionId, typeId)`：[源码 `apps/store/items/histories/esi.go`](https://github.com/raph5/eve-market-browser/blob/main/apps/store/items/histories/esi.go)。

## 逐项调查

### 1. Adam4EVE

#### 1.1 `tracker`：可用的精确单站日历史 API

官方 API 文档明确说明 tracker 每 10 分钟抓取订单簿并比较订单数量变化，以此估算发生的交易；参数支持 `date`、`locationID`、`typeID`、`isBuy` 和 `withGone`，其中默认 location 就是 `60003760`。返回 buy/sell 两侧的 `amount/high/low/avg/orderNum/iskValue`。

实际公开响应（Tritanium `34`，2026-09-01，Jita 4-4）：

```http
GET https://api.adam4eve.eu/v1/tracker?typeID=34&date=2026-09-01&locationID=60003760&withGone=0
```

```json
{
  "sell": {"amount":"2017938098","high":"3.90","low":"3.82","avg":"3.87","orderNum":"90","iskValue":"7835333849"},
  "buy":  {"amount":"231494039","high":"3.81","low":"3.65","avg":"3.72","orderNum":"68","iskValue":"860596601"}
}
```

证据与约束：

- [Adam4EVE 官方 API 文档](https://api.adam4eve.eu/)明确写出算法、参数、默认 Jita station、字段含义、必须提供带联系方式的 User-Agent，以及 **1 请求/5 秒**的限流。
- [上面的实际请求](https://api.adam4eve.eu/v1/tracker?typeID=34&date=2026-09-01&locationID=60003760&withGone=0)无需认证即可返回 JSON。
- 一次请求只接收一个 `date`，所以 30 日曲线需要 30 次请求。严格遵守限流时至少约 145 秒，不应在一条机器人命令的同步请求中串行完成。可在首次请求时并行度为 1 地抓取并缓存结果，或预先缓存第三方历史响应；这仍不是自行采样市场。
- 数据是**推断成交**：慢速市场较准确，高速市场会因 10 分钟间隔丢失细节。不能把 `avg` 宣称为 CCP 官方实际成交均价。

**适用图线**：`buy.avg`、`sell.avg`，可附带 low/high 阴影带。
**不适用图线**：每天某个固定时刻的最高收单、最低卖单。

#### 1.2 `MarketPricesStationHistory`：精确单站订单价日序列

Adam4EVE 的静态导出站点提供 `MarketPricesStationHistory`，按年、ISO 周和 hub/rest 分文件。实际读取 2026 年第 36 周 hub 文件，表头为：

```text
type_id;location_id;region_id;date;buy_price_low;buy_price_avg;buy_price_high;sell_price_low;sell_price_avg;sell_price_high
```

其中 `type_id=34, location_id=60003760` 的实际行包括：

```text
34;60003760;10000002;2026-08-31;3.62;3.75589;3.86;3.76;3.87143;3.9
34;60003760;10000002;2026-09-01;3.62;3.70537;3.81;3.67;3.86537;3.9
34;60003760;10000002;2026-09-02;3.62;3.72857;3.82;3.64;3.86232;3.9
```

这组字段是“当天观测到的最高收价/最低卖价的 low、日内平均、high”，最接近当前插件所需的 Jita best buy / best sell 走势。

证据与约束：

- [Adam4EVE 静态导出根目录](https://static.adam4eve.eu/)明确说明数据由 Adam4EVE 数据库每日导出。
- [Station History 年度目录](https://static.adam4eve.eu/MarketPricesStationHistory/)可见从 `2022/` 到当前年份的目录。
- [2026 年目录](https://static.adam4eve.eu/MarketPricesStationHistory/2026/)列出每周 `hub` 与 `rest` CSV。
- [2026-W36 hub CSV](https://static.adam4eve.eu/MarketPricesStationHistory/2026/MarketPricesStationHistory_hub_weekly_2026-36.csv)实测响应为 `text/csv`、允许跨域，`Content-Length: 27,302,078` 字节。
- 不需要 API key，也没有在下载站公布请求频率限制；仍应按周文件长期 HTTP 缓存，并使用 `Last-Modified`/`ETag` 做条件请求。
- 要覆盖任意连续 30 天通常需 5 个周文件，按近期体积估计原始下载约 130 MB。CSV 没有服务端 `type_id` 查询参数，客户端必须流式筛选目标物品和 `60003760`。

**可集成性判断：可集成，但不能在每次聊天查询时重新下载。** 推荐在应用服务端按需下载涉及的周文件、流式筛选并缓存筛选后的 30 个点。这里缓存的是第三方已经采集的历史文件，不是本地市场采样。

#### 1.3 `market_price_history`：不是单站

该端点支持 `typeID`、`regionID`、`start`、`end`，返回每天最高收单/最低卖单在一天内的 low/avg/high，但官方文档只允许五个 region ID，没有 `locationID` 参数。实测给请求附加 `locationID=60003760` 会被忽略，响应与不带该参数完全相同。

- [实际区域请求](https://api.adam4eve.eu/v1/market_price_history?typeID=34&start=2026-08-01&end=2026-09-01&regionID=10000002)
- [Adam4EVE 官方参数与字段说明](https://api.adam4eve.eu/)

它适合画 The Forge order-book-derived 曲线，不可标为 Jita 4-4。

#### 1.4 `hub_type_history.php`：单请求可取，但属于网页抓取

Adam4EVE 自己的单站物品历史页接受 `typeID`、`stationID` 和 `mode`。例如：

```text
https://www.adam4eve.eu/hub_type_history.php?typeID=34&stationID=60003760&mode=min
```

页面内嵌的第一个 Dygraph 数组按日期返回：

```text
Date, Buy High, Buy Low, Buy Avg, Sell High, Sell Low, Sell Avg
```

实测该页包含直到当天的长周期数据，单页约 140–165 KB，响应约 2–4 秒，因此从纯工程性能看，它比 30 次 `tracker` API 更适合聊天命令。但它是服务端渲染 HTML，不是 Adam4EVE 公布的 REST API；解析器必须防范页面格式改变，并在失败时降级到 ESI 区域历史或只返回文字价格。图注仍需遵循页面自己的说明：数据由 A4E 多次每小时记录订单簿变化得到，是估算值。

### 2. Janice

Janice v2 OpenAPI 仅公开 appraisal、markets、pricer 等路由，没有 history/time-series 路由。`PricerItemValues` 和 `AppraisalItemValues` 中虽然有：

- `buyPrice5DayMedian` / `sellPrice5DayMedian`
- `buyPrice30DayMedian` / `sellPrice30DayMedian`
- 相应 `splitPrice...Median`

但这些各是单个区间中位数，不含日期数组，不能重建 30 个点。Jita 在其市场枚举中使用 `market=2`。

证据：

- [Janice v2 OpenAPI JSON](https://janice.e-351.com/api/rest/v2/swagger.json)：实际核对 `paths` 仅有 appraisal、industry、markets、pricer；schema 只有上述聚合字段。
- 同一 OpenAPI 的 `securitySchemes` 指定请求头 `X-ApiKey`，并说明需在 Discord 开 ticket 申请；文档未公布具体限流数字。
- [Janice 官方示例源码](https://github.com/E-351/janice/blob/master/janice-v2.gs)定义 API base 和 `jita: 2`，并提醒滥用流量可能被封禁。

**结论：不能用于 30 日走势图；最多作为图旁的“30 日中位数”参考线。**

### 3. Fuzzwork Market Data

Fuzzwork 官方 API 页面提供 `aggregates`，接受 `station=60003760`，所以可以精确得到当前 Jita 4-4 的订单聚合。实际请求：

```http
GET https://market.fuzzwork.co.uk/aggregates/?station=60003760&types=34
```

返回 buy/sell 的当前 `weightedAverage/max/min/stddev/median/volume/orderCount/percentile`。但文档没有日期、起止时间或历史端点；`orderset` 也只返回最近订单集 ID。

- [Fuzzwork 官方 API 文档](https://market.fuzzwork.co.uk/api/)
- [实际 station 聚合响应](https://market.fuzzwork.co.uk/aggregates/?station=60003760&types=34)

无需认证；官方页面没有给出明确硬限额。**只能用于当前价格，不能提供 30 天历史。**

### 4. EVE Tycoon

EVE Tycoon 有两组容易混淆的接口：

1. `/api/v1/market/stats/{regionId}/{typeId}?locationId=60003760`：当前统计可以筛到 Jita 4-4，约每 5 分钟更新。
2. `/api/v1/market/history/{regionId}/{typeId}`：历史接口只有 region/type，没有 `locationId`；官方文档明确称其为 ESI region history 的镜像，每日更新。

实际历史响应从 2019 年开始，字段为 `date/regionId/typeId/average/highest/lowest/orderCount/volume`，与 ESI 区域成交历史语义一致。

- [EVE Tycoon 官方 API 文档](https://evetycoon.com/docs)
- [The Forge Tritanium 实际历史响应](https://evetycoon.com/api/v1/market/history/10000002/34)
- [Jita 4-4 当前 stats 实际响应](https://evetycoon.com/api/v1/market/stats/10000002/34?locationId=60003760)

公开 market API 无需认证。文档没有给固定每分钟限额，而是要求尊重响应的 `Expires`；历史每日更新，stats 约 5 分钟更新。**可作为 ESI 区域历史的方便镜像，但不能提供单站历史。**

### 5. Goonmetrics

Goonmetrics 的 API 文档也将两者分开：

- `price_data` 接收 `station_id`，返回当前站点最高收单、最低卖单和挂牌量；
- `price_history` 明确接收 `region_id`，返回最近 30 天区域 `minPrice/maxPrice/avgPrice/movement/numOrders`。

实际请求均无需认证并返回 XML：

- [Jita 4-4 当前 Tritanium](https://goonmetrics.apps.goonswarm.org/api/price_data/?station_id=60003760&type_id=34)
- [The Forge 最近 30 天 Tritanium](https://goonmetrics.apps.goonswarm.org/api/price_history/?region_id=10000002&type_id=34)
- [Goonmetrics 官方 API 文档](https://goonmetrics.apps.goonswarm.org/api/)

文档未声明限流。**历史仍然是区域成交历史，不满足单站要求。**

### 6. EVE Marketer

EVEMarketer 的公开 marketstat 接口只提供当前 buy/sell 聚合，可按 `regionlimit` 或 `usesystem` 过滤；Jita 示例使用 system `30000142`，不是 station `60003760`。没有可验证的 30 日历史端点。

- [EVE University 对 EVEMarketer API 参数和响应的说明](https://wiki.eveuniversity.org/API_access_to_market_data)
- 实测 `https://api.evemarketer.com/ec/marketstat/json?typeid=34&usesystem=30000142` 于 2026-09-11 返回 HTTP 503。

**结论：既没有单站历史，当前服务状态也不适合作为新集成依赖。**

### 7. EVE Workbench

未找到 EVE Workbench 面向第三方、稳定公开且涵盖 market history 的正式 API 文档或 OpenAPI。调查中发现的 staging Swagger 页面当前无法加载其 `/swagger/v1/swagger.json`；对猜测的生产 API 路径请求返回的是前端 SPA HTML，而不是 JSON。这不足以构成可依赖的接口合约。

- [EVE Workbench staging Swagger](https://api.staging.eveworkbench.com/swagger/index.html)当前显示 API definition Not Found。
- [EVE Workbench 网站](https://www.eveworkbench.com/)未提供可核验的 Jita 4-4 历史 API 文档。

**结论：不要通过抓取网页或逆向内部接口集成。** 如未来官方发布 API，应重新核对 location/date 参数、认证和使用条款。

### 8. EVE Market Browser（evemarketbrowser.com）

该项目源码公开。源码证据表明其 history 后端直接请求 ESI 的 region history；前端内部 store 路径也是 `/history?region=...&type=...`，没有 station 参数。站点位置只存在于当前 order book 展示。

- [项目源码仓库](https://github.com/raph5/eve-market-browser)
- [ESI history 获取实现](https://github.com/raph5/eve-market-browser/blob/main/apps/store/items/histories/esi.go)
- [网站到内部 store 的 history 请求](https://github.com/raph5/eve-market-browser/blob/main/apps/website/app/esiStore/goStore.ts)

项目没有把内部 Unix-socket store 声明为公共第三方 API。**其图表是区域成交历史，不能用于精确 Jita 4-4 历史，也不应依赖未公开的站内路由。**

### 9. EveKit（历史方案，现不可用）

EveKit 曾归档区域完整 order book 的 5 分钟快照。每条 order 带 `LOCATION ID`，理论上可从 The Forge 文件筛选 `60003760`，而且历史可追溯到 2016；这属于“区域订单簿快照中筛出单站”，并非区域成交历史。

- [EveKit Market Data 格式文档](https://evekit-documentation.readthedocs.io/en/latest/other/marketdata.html)
- [EveKit marketdata server 源码说明](https://github.com/OrbitalEnterprises/evekit-marketdata-server/blob/master/SERVICES.md)
- 但维护者已发布 [EveKit 永久关闭公告](https://forums.eveonline.com/t/evekit-shutting-down-permanently-effective-2019-12-15/192377)，明确包含 market data 服务；当前线上域名也无法正常建立可靠连接。

**结论：历史上满足需求，但现在不能作为生产依赖。**

## 推荐实施方案

### 方案 A：Adam4EVE tracker（推荐先落地）

适用于接受“推断成交价格走势”的产品定义。

1. 对唯一匹配的 `type_id`，请求最近 30 个 UTC 日期的 `tracker`。
2. 固定 `locationID=60003760&withGone=0`，显式设置带联系方式的 User-Agent。
3. 全局限速到每 5 秒最多一次；第三方返回按 `type_id + date` 缓存至少 24 小时，历史日期可长期缓存。
4. 图中绘制 `sell.avg` 与 `buy.avg` 两条线；可用 `low/high` 做范围带。
5. 图注写明：`Jita 4-4 · 基于 Adam4EVE 每 10 分钟订单簿变化推断的成交数据`。
6. 首次 30 天冷启动耗时过长，不要阻塞机器人命令。可以异步生成后发送图片，或先返回当前价格并提示走势图生成中。

优点：响应小、字段直接、精确到站、无需 API key。
缺点：30 次请求与严格限流；数据是估算成交，不是 best bid/ask。

### 方案 B：Adam4EVE station-history CSV（要求最高收/最低卖曲线时推荐）

1. 根据 30 天日期范围计算涉及的 ISO 周（通常 5 周）。
2. 下载对应 `MarketPricesStationHistory_hub_weekly_YYYY-WW.csv`，使用 HTTP 条件请求并缓存原文件或筛选结果。
3. 流式解析分号分隔 CSV，只保留 `type_id == 查询物品` 且 `location_id == 60003760` 的行。
4. 画 `buy_price_avg` 与 `sell_price_avg`；如果产品希望展示日内区间，再叠加 low/high 范围。
5. 当前日尚未进入完成的日导出时，用现有实时 Jita 查询结果补一个“当前”点，并明确它不是完整日均值。

优点：精确到站，直接表达 Jita 最高收单/最低卖单在日内的变化，历史跨度足够。
缺点：下载量大，文件目录与命名不是版本化 API 合约；必须容忍缺周、迟到和格式变化。

### 不推荐

- 不要把 ESI、EVE Tycoon、Goonmetrics 或 EVE Market Browser 的 The Forge 历史标成“Jita 4-4 历史”。
- 不要用 Janice 的 30 日中位数伪造 30 个日数据点。
- 不要逆向 EVE Workbench 或 EVE Market Browser 的内部网页接口作为生产依赖。
- 不要依赖已关闭的 EveKit 在线服务。

## 最终建议

从集成成本与用户认知平衡看，建议采用两阶段策略：

1. **第一阶段**：集成 Adam4EVE tracker，图表标题写“Jita 4-4 近 30 日推断成交价”，画 buy/sell average；历史结果长期缓存，避免每次承担 150 秒冷启动。
2. **如果业务坚持当前报价语义**（最低卖价/最高收价必须与现有查价一致）：改用 Adam4EVE station-history CSV，图表画 `sell_price_avg` / `buy_price_avg`，并接受较大的首次下载量。

两者都满足“不本地自行采样”：价格历史由 Adam4EVE 已有数据库提供。本地仅为性能缓存第三方响应，不生成新的市场历史事实。
