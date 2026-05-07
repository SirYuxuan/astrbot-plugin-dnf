import asyncio
import datetime
import os
import re

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register

from .dnf_plugin.config import PluginConfig
from .dnf_plugin.dnf_utils import DnfGoldRatioFetcher
from .dnf_plugin.egg_utils import fetch_egg_prices, format_egg_items, format_egg_prices, parse_egg_args
from .dnf_plugin.image_utils import ImageGenerator
from .dnf_plugin.oil_utils import calculate_oil_cost, fetch_oil_data, format_oil_info, get_oil_price_by_type, has_oil_price_changed
from .dnf_plugin.storage_utils import JsonFileStore


@register("yuxuandnf", "Sir 丶雨轩", "雨轩DNF 查询插件，支持金币比例、油价和蛋价查询。", "v1.4")
class DNF_Plugin(Star):
    _tasks_started = False
    _tasks: list[asyncio.Task] = []

    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.store = JsonFileStore(self.base_dir)
        self.config = PluginConfig(config)
        self.image_generator = ImageGenerator(self.config.section("image_ai"))

        self.last_avg_ratio = self._load_float("last_avg_ratio.json", "last_avg_ratio")
        self.last_sent_avg_ratio = self._load_float("last_sent_avg_ratio.json", "last_sent_avg_ratio")
        self.last_oil_data = self.store.load("last_oil_data.json", {})
        if not isinstance(self.last_oil_data, dict):
            self.last_oil_data = {}
        self.last_egg_sent_date = self._load_string("last_egg_sent_date.json", "last_egg_sent_date")

        if not DNF_Plugin._tasks_started:
            DNF_Plugin._tasks_started = True
            loop = asyncio.get_event_loop()
            DNF_Plugin._tasks = []
            if self.config.get("gold.monitor_enabled", True):
                DNF_Plugin._tasks.append(loop.create_task(self.scheduled_gold_ratio_task()))
            if self.config.get("oil.monitor_enabled", True):
                DNF_Plugin._tasks.append(loop.create_task(self.oil_price_daily_task()))
            if self.config.get("egg.monitor_enabled", True):
                DNF_Plugin._tasks.append(loop.create_task(self.egg_price_hourly_task()))

    def _load_float(self, filename: str, key: str) -> float | None:
        data = self.store.load(filename, {})
        if not isinstance(data, dict) or data.get(key) is None:
            return None
        try:
            return float(data[key])
        except Exception:
            logger.error(f"状态字段不是有效数字 {filename}:{key}")
            return None

    def _load_string(self, filename: str, key: str) -> str | None:
        data = self.store.load(filename, {})
        if not isinstance(data, dict) or not data.get(key):
            return None
        return str(data[key])

    def _save_last_avg_ratio(self) -> None:
        self.store.save("last_avg_ratio.json", {"last_avg_ratio": self.last_avg_ratio})

    def _save_last_sent_avg_ratio(self) -> None:
        self.store.save("last_sent_avg_ratio.json", {"last_sent_avg_ratio": self.last_sent_avg_ratio})

    def _save_last_oil_data(self) -> None:
        self.store.save("last_oil_data.json", self.last_oil_data)

    def _save_last_egg_sent_date(self) -> None:
        self.store.save("last_egg_sent_date.json", {"last_egg_sent_date": self.last_egg_sent_date})

    def _get_message_text(self, event) -> str:
        if hasattr(event, "message_str"):
            return event.message_str
        if hasattr(event, "get_message_str"):
            return event.get_message_str()
        if hasattr(event, "message_obj"):
            return str(event.message_obj)
        return str(event)

    def _parse_image_prompt(self, message: str, command: str) -> str:
        prompt = message.split(command, 1)[1].strip() if command in message else ""
        return prompt.replace("[图片]", "").strip()

    async def _get_first_image_path(self, event) -> str | None:
        messages = event.get_messages() if hasattr(event, "get_messages") else []
        for component in messages:
            component_type = str(getattr(component, "type", "")).lower()
            if "image" not in component_type:
                continue
            for attr in ("url", "file"):
                value = str(getattr(component, attr, "") or "")
                if value.startswith(("http://", "https://")):
                    return value
            if hasattr(component, "convert_to_file_path"):
                try:
                    return await component.convert_to_file_path()
                except Exception as e:
                    logger.error(f"图片消息转换为本地文件失败: {e}")
            for attr in ("path", "file", "url"):
                value = getattr(component, attr, "")
                if value:
                    return str(value)
        return None

    def _get_aiocqhttp_client(self):
        platform_name = self.config.get("platform.name", "aiocqhttp")
        for platform in self.context.platform_manager.get_insts():
            if platform.meta().name == platform_name:
                return platform.get_client()
        return None

    def _parse_avg_ratio(self, ratio_text: str) -> float | None:
        match = re.search(r"均价：1元=([\d.]+)万金币", ratio_text)
        return float(match.group(1)) if match else None

    async def initialize(self):
        """AstrBot plugin lifecycle hook."""

    async def scheduled_gold_ratio_task(self):
        logger.info("金币比例定时任务已启动，每分钟检测一次")
        while True:
            try:
                client = self._get_aiocqhttp_client()
                if client:
                    ratio_text = await asyncio.to_thread(DnfGoldRatioFetcher.fetch_gold_ratio_text)
                    avg_ratio = self._parse_avg_ratio(ratio_text)
                    if avg_ratio is None:
                        logger.info("未能获取到金币均价数据")
                    else:
                        await self._maybe_send_gold_ratio_notice(client, avg_ratio)
                        self.last_avg_ratio = avg_ratio
                        self._save_last_avg_ratio()
                await asyncio.sleep(max(10, int(self.config.get("gold.interval_seconds", 60))))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"金币比例定时任务执行失败: {e}")
                await asyncio.sleep(30)

    async def _maybe_send_gold_ratio_notice(self, client, avg_ratio: float) -> None:
        if self.last_sent_avg_ratio is None:
            message = f"首次监控，当前金币均价：{avg_ratio:.2f}万金币"
        else:
            diff = avg_ratio - self.last_sent_avg_ratio
            if abs(diff) < float(self.config.get("gold.change_threshold", 2.0)):
                return
            message = (
                f"金币比例波动：上次发送均价 {self.last_sent_avg_ratio:.2f}，"
                f"本次均价 {avg_ratio:.2f}，变动 {diff:+.2f}万金币"
            )

        await client.send_group_msg(group_id=int(self.config.get("gold.notify_group_id", 101344113)), message=message)
        self.last_sent_avg_ratio = avg_ratio
        self._save_last_sent_avg_ratio()

    async def oil_price_daily_task(self):
        await asyncio.sleep(2)
        try:
            if self.config.get("oil.startup_notice_enabled", True):
                await self._send_startup_oil_notice()
            while True:
                now = datetime.datetime.now()
                check_hour = min(23, max(0, int(self.config.get("oil.check_hour", 8))))
                target = now.replace(hour=check_hour, minute=0, second=0, microsecond=0)
                if now >= target:
                    target += datetime.timedelta(days=1)
                await asyncio.sleep((target - now).total_seconds())
                await self._check_and_send_oil_changes()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"油价每日任务异常: {e}")

    async def _send_startup_oil_notice(self) -> None:
        client = self._get_aiocqhttp_client()
        infos = []
        for area in self._configured_oil_areas():
            oil = await asyncio.to_thread(fetch_oil_data, area)
            if oil:
                infos.append(format_oil_info(oil))
                self.last_oil_data[area] = oil

        if infos and client:
            try:
                await client.send_group_msg(
                    group_id=int(self.config.get("oil.notify_group_id", 101344113)),
                    message="油价更新通知：\n\n" + "\n".join(infos),
                )
            except Exception as e:
                logger.error(f"发送启动时油价通知失败: {e}")
        self._save_last_oil_data()

    async def _check_and_send_oil_changes(self) -> None:
        client = self._get_aiocqhttp_client()
        changed_infos = []
        for area in self._configured_oil_areas():
            oil = await asyncio.to_thread(fetch_oil_data, area)
            if not oil:
                continue
            if has_oil_price_changed(self.last_oil_data.get(area), oil):
                changed_infos.append(format_oil_info(oil))
                self.last_oil_data[area] = oil

        if changed_infos and client:
            try:
                await client.send_group_msg(
                    group_id=int(self.config.get("oil.notify_group_id", 101344113)),
                    message="油价更新通知：\n\n" + "\n".join(changed_infos),
                )
            except Exception as e:
                logger.error(f"发送油价更新通知失败: {e}")
        if changed_infos:
            self._save_last_oil_data()

    async def egg_price_hourly_task(self):
        await asyncio.sleep(2)
        try:
            while True:
                today = datetime.date.today().strftime("%Y-%m-%d")
                if self.last_egg_sent_date != today:
                    await self._send_daily_egg_notice(today)
                await asyncio.sleep(max(60, int(self.config.get("egg.interval_seconds", 3600))))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"蛋价每小时任务异常: {e}")

    async def _send_daily_egg_notice(self, today: str) -> None:
        date_str = datetime.date.today().strftime("%Y%m%d")
        items = await asyncio.to_thread(fetch_egg_prices, str(self.config.get("egg.monitor_area", "平舆")), date_str)
        if not items:
            return

        message = format_egg_items(items, [], datetime.date.today(), limit=int(self.config.get("egg.daily_limit", 10)))
        client = self._get_aiocqhttp_client()
        if not client:
            return

        try:
            await client.send_group_msg(group_id=int(self.config.get("egg.notify_group_id", 527189909)), message=message)
            self.last_egg_sent_date = today
            self._save_last_egg_sent_date()
        except Exception as e:
            logger.error(f"发送蛋价群消息失败: {e}")

    @filter.command("金币比例")
    async def dnf_gold_ratio(self, event):
        """查询 DNF 金币比例"""
        ratio_text = await asyncio.to_thread(DnfGoldRatioFetcher.fetch_gold_ratio_text)
        yield event.plain_result(ratio_text)

    @filter.command("油价")
    async def oil_price(self, event):
        """查询油价信息或计算行驶成本"""
        try:
            message = self._get_message_text(event)
            calc_match = re.search(r"油价\s+([^\s]+)\s+(\d+)\s+([\d.]+)(?:\s+(\d+))?", message)
            if calc_match:
                area = calc_match.group(1)
                oil_type = calc_match.group(2)
                consumption = float(calc_match.group(3))
                distance = int(calc_match.group(4)) if calc_match.group(4) else 100

                oil_data = await asyncio.to_thread(fetch_oil_data, area)
                oil_price = get_oil_price_by_type(oil_data or {}, oil_type)
                if oil_price is None:
                    yield event.plain_result(f"❌ 无法获取{area}地区{oil_type}号油的价格信息")
                    return

                yield event.plain_result(calculate_oil_cost(oil_type, oil_price, consumption, distance, area))
                return

            area_match = re.search(r"油价\s+([^\s\d]+)$", message)
            if area_match:
                area = area_match.group(1).strip()
                oil_data = await asyncio.to_thread(fetch_oil_data, area)
                if oil_data:
                    yield event.plain_result(format_oil_info(oil_data))
                else:
                    yield event.plain_result(f"查询失败：未能获取{area}油价数据")
                return

            yield event.plain_result(
                "❌ 参数格式不正确\n\n"
                "📋 正确格式：\n"
                "• 油价 地区名 - 查询地区油价\n"
                "• 油价 地区名 油号 油耗 - 计算行驶成本\n"
                "• 油价 地区名 油号 油耗 里程 - 计算指定里程成本"
            )
        except Exception as e:
            logger.error(f"油价查询异常: {e}")
            yield event.plain_result("油价查询出现异常，请稍后重试")

    @filter.command("蛋价")
    async def egg_price(self, event):
        """查询蛋价，示例：蛋价 驻马店 或 蛋价 驻马店 20260129"""
        try:
            area, date_str = parse_egg_args(self._get_message_text(event))
            text = await asyncio.to_thread(format_egg_prices, area, date_str, int(self.config.get("egg.daily_limit", 10)))
            yield event.plain_result(text)
        except Exception as e:
            logger.error(f"蛋价查询异常: {e}")
            yield event.plain_result("蛋价查询出现异常，请稍后重试")

    @filter.command("画图")
    async def draw_image(self, event):
        """使用配置的图片生成 API 生成图片，用法：画图 <提示词>"""
        try:
            message = self._get_message_text(event)
            prompt = self._parse_image_prompt(message, "画图")
            if not prompt:
                yield event.plain_result("请输入图片描述，例如：画图 一张地下城冒险风格头像")
                return
            if not self.image_generator.can_edit():
                yield event.plain_result("图片生成功能未启用或配置不完整，请先在插件配置中填写 image_ai")
                return

            yield event.plain_result(f"正在生成图片，请稍候...\n提示词：{prompt}")
            file_path, error = await asyncio.to_thread(self.image_generator.generate, prompt)
            if error:
                yield event.plain_result(f"图片生成失败：{error}")
                return

            yield event.image_result(file_path)
            if file_path:
                try:
                    os.unlink(file_path)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"画图命令异常: {e}")
            yield event.plain_result(f"画图出现异常：{e}")

    @filter.command("生图")
    async def set_image_quality(self, event):
        """切换图片生成质量，用法：生图 1/2/3"""
        try:
            message = self._get_message_text(event)
            match = re.search(r"生图\s+([123])(?:\s|$)", message)
            if not match:
                yield event.plain_result("请输入生图质量：生图 1=low，生图 2=medium，生图 3=high")
                return

            quality_map = {"1": "low", "2": "medium", "3": "high"}
            quality = quality_map[match.group(1)]
            self.config.set("image_ai.quality", quality)
            self.image_generator.quality = quality
            yield event.plain_result(f"已切换图片生成质量：{quality}")
        except Exception as e:
            logger.error(f"切换图片生成质量异常: {e}")
            yield event.plain_result(f"切换图片生成质量出现异常：{e}")

    @filter.regex(r"/?图生图")
    async def edit_image(self, event):
        """使用配置的图片生成 API 修改图片，用法：图生图 <图片> <提示词>"""
        try:
            message = self._get_message_text(event)
            prompt = self._parse_image_prompt(message, "图生图")
            if not prompt:
                yield event.plain_result("请输入修改描述，例如：图生图 [图片] 改成地下城冒险风格头像")
                return
            if not self.image_generator.is_ready():
                yield event.plain_result("图片生成功能未启用或配置不完整，请先在插件配置中填写 image_ai")
                return

            image_path = await self._get_first_image_path(event)
            if not image_path:
                yield event.plain_result("请在消息中附带一张图片，例如：图生图 [图片] 改成地下城冒险风格头像")
                return

            yield event.plain_result(f"正在根据图片生成，请稍候...\n提示词：{prompt}")
            file_path, error = await asyncio.to_thread(self.image_generator.edit, image_path, prompt)
            if error:
                yield event.plain_result(f"图生图失败：{error}")
                return

            yield event.image_result(file_path)
            if file_path:
                try:
                    os.unlink(file_path)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"图生图命令异常: {e}")
            yield event.plain_result(f"图生图出现异常：{e}")

    def _configured_oil_areas(self) -> list[str]:
        areas = self.config.get("oil.monitor_areas", ["河南"])
        if not isinstance(areas, list):
            return ["河南"]
        return [str(area).strip() for area in areas if str(area).strip()]

    async def terminate(self):
        for task in DNF_Plugin._tasks:
            task.cancel()
        if DNF_Plugin._tasks:
            await asyncio.gather(*DNF_Plugin._tasks, return_exceptions=True)
        DNF_Plugin._tasks = []
        DNF_Plugin._tasks_started = False
