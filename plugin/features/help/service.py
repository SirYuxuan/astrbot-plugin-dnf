class HelpFeature:
    TEXT = (
        "【烟雨机器人插件帮助】\n"
        "/油价 河南\n"
        "查询地区油价及行驶成本\n"
        "/jt 毒蜥级\n"
        "查询 EVE 吉他市场价格\n"
        "/col 中级水晶\n"
        "查询并汇总多个物品价格\n"
        "/金币比例\n"
        "查询 DNF 金币比例\n"
        "/rat\n"
        "查询刷怪、纳税及净收入（需在管理系统注册）\n"
        "/subrat\n"
        "订阅或取消每天 23:50 的 RAT 私聊报告\n"
        "/info\n"
        "查询 EVE 绑定信息（需在管理系统注册）\n"
        "/tr raven\n"
        "翻译 EVE 中英文名称（可用 kind=type 筛选）\n"
        "/nav ALL 吉他\n"
        '为绑定角色设置导航；指定角色可写 /nav "角色名" 星系\n'
        "/where 乌鸦级\n"
        "按 QQ 搜索已同步的资产位置和数量\n"
        '/fleet "主角色名" ALL\n'
        "由已在舰队的主角色邀请同 QQ 下其他角色，也可指定目标角色名\n"
        "/kb Yuxan Axiom\n"
        "查询角色 zKillboard 战绩；军团或联盟可用 /kb 军团 名称、/kb 联盟 名称\n"
        "/timer 2天2小时5分\n"
        "计算指定时长后的 EVE 时间和北京时间\n"
        "/status\n"
        "查询 EVE 服务器状态和在线人数\n"
        "/ship 乌鸦级\n"
        "查询舰船槽位、挂点和加成\n"
        "/train 乌鸦级\n"
        "查询绑定角色的舰船立即训练时间\n"
        "/subkb\n"
        "订阅或取消军团 KB 私聊通知（请在群聊中使用）\n"
        "/suballkb\n"
        "订阅或取消联盟 KB 通知（请在 KOOK 频道中使用）"
    )

    async def query(self) -> str:
        return self.TEXT
