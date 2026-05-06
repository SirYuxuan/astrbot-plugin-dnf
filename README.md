# yuxuandnf

雨轩 DNF 查询插件，基于 AstrBot 插件系统开发。

## 功能

- 查询 DNF 金币比例，数据来源于 DD373
- 查询全国各地区油价，数据来源于 iamwawa.cn
- 按地区、油号、油耗和里程计算行驶成本
- 查询蛋价，并支持每日群推送
- 定时监控金币比例和油价变动
- 可选启用 `/画图`，通过插件配置接入图片生成 API

## 指令

### 金币比例

```text
/金币比例
```

### 油价

```text
/油价 河南
/油价 河南 92 7.5
/油价 河南 95 8.0 100
```

参数说明：

- `油价 地区名`：查询地区油价
- `油价 地区名 油号 油耗`：按默认 100 公里计算成本
- `油价 地区名 油号 油耗 里程`：按指定里程计算成本

### 蛋价

```text
/蛋价 平舆
/蛋价 平舆 20260506
```

### 画图

默认关闭。先在插件配置里启用 `image_ai.enabled`，并填写 `endpoint` 和 `api_key`。

```text
/画图 一张地下城冒险风格头像
```

## 插件配置

项目提供 `_conf_schema.json`，AstrBot 会在 WebUI 中生成可视化配置项。

可配置内容包括：

- 主动推送平台名称
- 金币比例监控开关、推送群号、检测间隔、波动阈值
- 油价监控开关、推送群号、监控地区、每日检查时间、启动通知
- 蛋价监控开关、推送群号、监控地区、检测间隔、展示条数
- 图片生成 API 开关、接口地址、密钥、鉴权 Header、尺寸、质量、输出格式、超时时间

## 项目结构

```text
.
├── main.py              # AstrBot 插件入口、命令和定时任务编排
├── _conf_schema.json    # AstrBot 插件配置 schema
├── dnf_plugin/
│   ├── config.py        # 配置默认值和读取封装
│   ├── dnf_utils.py     # DNF 金币比例查询
│   ├── egg_utils.py     # 蛋价查询、解析和格式化
│   ├── image_utils.py   # 可配置图片生成客户端
│   ├── oil_utils.py     # 油价查询、格式化和成本计算
│   └── storage_utils.py # JSON 状态文件读写
├── metadata.yaml        # AstrBot 插件元信息
└── requirements.txt     # 运行依赖
```

## 运行依赖

```text
requests
```

## 运行时状态

插件会在目录下生成以下运行时状态文件，用于避免重启后重复推送：

- `last_avg_ratio.json`
- `last_sent_avg_ratio.json`
- `last_oil_data.json`
- `last_egg_sent_date.json`

这些文件已加入 `.gitignore`，不需要提交到仓库。
