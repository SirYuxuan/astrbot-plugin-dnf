import os
import re

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.message_components import Record
from astrbot.api.star import Context, Star, register

from .dnf_plugin.config import PluginConfig
from .dnf_plugin.features.egg import EggFeature
from .dnf_plugin.features.gold import GoldFeature
from .dnf_plugin.features.image_feature import ImageFeature
from .dnf_plugin.features.oil import OilFeature
from .dnf_plugin.image_utils import ImageGenerator
from .dnf_plugin.music_utils import MusicGenerator
from .dnf_plugin.storage_utils import JsonFileStore


@register("yuxuandnf", "Sir 丶雨轩", "雨轩DNF 查询插件，支持金币比例、油价和蛋价查询。", "v1.4")
class DNF_Plugin(Star):
    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        store = JsonFileStore(base_dir)
        cfg = PluginConfig(config)

        self.gold = GoldFeature(cfg, store, context)
        self.oil = OilFeature(cfg, store, context)
        self.egg = EggFeature(cfg, store, context)
        self.image = ImageFeature(ImageGenerator(cfg.section("image_ai")), cfg)
        self.music = MusicGenerator(cfg.section("music_ai"))

    async def initialize(self) -> None:
        self.gold.start()
        self.oil.start()
        self.egg.start()

    # ── 金币比例 ────────────────────────────────────────────────────────────

    @filter.command("金币比例")
    async def dnf_gold_ratio(self, event):
        """查询 DNF 金币比例"""
        yield event.plain_result(await self.gold.query())

    # ── 油价 ────────────────────────────────────────────────────────────────

    @filter.command("油价")
    async def oil_price(self, event):
        """查询油价，或计算行驶成本。示例：油价 河南 / 油价 河南 92 8 500"""
        try:
            yield event.plain_result(await self.oil.query(self._msg(event)))
        except Exception as e:
            logger.error(f"油价查询异常: {e}")
            yield event.plain_result("油价查询出现异常，请稍后重试")

    # ── 蛋价 ────────────────────────────────────────────────────────────────

    @filter.command("蛋价")
    async def egg_price(self, event):
        """查询蛋价。示例：蛋价 驻马店 / 蛋价 驻马店 20260129"""
        try:
            yield event.plain_result(await self.egg.query(self._msg(event)))
        except Exception as e:
            logger.error(f"蛋价查询异常: {e}")
            yield event.plain_result("蛋价查询出现异常，请稍后重试")

    # ── 图片生成 ─────────────────────────────────────────────────────────────

    @filter.command("写歌")
    async def write_song(self, event):
        """使用 FAL 生成音乐。用法：写歌 <创作需求>，可换行补充歌词。"""
        audio_path = None
        try:
            content = self._msg(event).split("写歌", 1)[-1].strip()
            prompt, _, lyrics = content.partition("\n")
            if not prompt:
                yield event.plain_result("请输入写歌需求，例如：写歌 温暖女声的中文民谣")
                return
            if not self.music.is_ready():
                yield event.plain_result("写歌功能未启用或配置不完整，请先在插件配置中填写 music_ai")
                return
            yield event.plain_result(f"正在写歌，请稍候...\n风格：{prompt}")
            audio_path, audio_url, error = await asyncio.to_thread(self.music.generate, prompt, lyrics.strip())
            if error:
                yield event.plain_result(f"写歌失败：{error}")
                return
            if audio_path:
                yield event.chain_result([Record.fromFileSystem(audio_path)])
            else:
                yield event.plain_result(f"写歌完成：{audio_url}")
        except Exception as e:
            logger.error(f"写歌命令异常: {e}")
            yield event.plain_result(f"写歌出现异常：{e}")
        finally:
            if audio_path:
                try:
                    os.unlink(audio_path)
                except OSError:
                    pass

    @filter.command("画图")
    async def draw_image(self, event):
        """文生图。示例：画图 一张地下城冒险风格头像"""
        try:
            prompt = self.image.parse_prompt(self._msg(event), "画图")
            if not prompt:
                yield event.plain_result("请输入图片描述，例如：画图 一张地下城冒险风格头像")
                return
            if not self.image.generator.can_generate():
                yield event.plain_result("图片生成功能未启用或配置不完整，请先在插件配置中填写 image_ai")
                return
            yield event.plain_result(f"正在生成图片，请稍候...\n提示词：{prompt}")
            file_path, error = await self.image.generate(prompt)
            if error:
                yield event.plain_result(f"图片生成失败：{error}")
                return
            yield event.image_result(file_path)
            self.image.cleanup(file_path)
        except Exception as e:
            logger.error(f"画图命令异常: {e}")
            yield event.plain_result(f"画图出现异常：{e}")

    @filter.command("生图")
    async def set_image_quality(self, event):
        """切换图片生成质量。用法：生图 1=low / 2=medium / 3=high"""
        try:
            match = re.search(r"生图\s+([123])(?:\s|$)", self._msg(event))
            if not match:
                yield event.plain_result("请输入质量档位：生图 1=low，生图 2=medium，生图 3=high")
                return
            quality = {"1": "low", "2": "medium", "3": "high"}[match.group(1)]
            self.image.set_quality(quality)
            yield event.plain_result(f"已切换图片生成质量：{quality}")
        except Exception as e:
            logger.error(f"切换图片生成质量异常: {e}")
            yield event.plain_result(f"切换质量出现异常：{e}")

    @filter.regex(r"/?图生图")
    async def edit_image(self, event):
        """图生图。用法：图生图 [图片] 改成地下城冒险风格"""
        try:
            prompt = self.image.parse_prompt(self._msg(event), "图生图")
            if not prompt:
                yield event.plain_result("请输入修改描述，例如：图生图 [图片] 改成地下城冒险风格头像")
                return
            if not self.image.generator.is_ready():
                yield event.plain_result("图片生成功能未启用或配置不完整，请先在插件配置中填写 image_ai")
                return
            image_path = await self.image.get_first_image_path(event)
            if not image_path:
                yield event.plain_result("请在消息中附带一张图片，例如：图生图 [图片] 改成地下城冒险风格头像")
                return
            yield event.plain_result(f"正在根据图片生成，请稍候...\n提示词：{prompt}")
            file_path, error = await self.image.edit(image_path, prompt)
            if error:
                yield event.plain_result(f"图生图失败：{error}")
                return
            yield event.image_result(file_path)
            self.image.cleanup(file_path)
        except Exception as e:
            logger.error(f"图生图命令异常: {e}")
            yield event.plain_result(f"图生图出现异常：{e}")

    # ── 生命周期 ─────────────────────────────────────────────────────────────

    async def terminate(self) -> None:
        await self.gold.stop()
        await self.oil.stop()
        await self.egg.stop()

    # ── 工具方法 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _msg(event) -> str:
        if hasattr(event, "message_str"):
            return event.message_str
        if hasattr(event, "get_message_str"):
            return event.get_message_str()
        return str(event)
