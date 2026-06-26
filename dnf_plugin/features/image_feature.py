import asyncio
import os

from astrbot.api import logger

from ..image_utils import ImageGenerator


class ImageFeature:
    def __init__(self, generator: ImageGenerator, config) -> None:
        self.generator = generator
        self.config = config

    def parse_prompt(self, message: str, command: str) -> str:
        prompt = message.split(command, 1)[1].strip() if command in message else ""
        return prompt.replace("[图片]", "").strip()

    async def get_first_image_path(self, event) -> str | None:
        messages = event.get_messages() if hasattr(event, "get_messages") else []
        for component in messages:
            if "image" not in str(getattr(component, "type", "")).lower():
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

    async def generate(self, prompt: str) -> tuple[str | None, str | None]:
        return await asyncio.to_thread(self.generator.generate, prompt)

    async def edit(self, image_path: str, prompt: str) -> tuple[str | None, str | None]:
        return await asyncio.to_thread(self.generator.edit, image_path, prompt)

    def set_quality(self, quality: str) -> None:
        self.config.set("image_ai.quality", quality)
        self.generator.quality = quality

    @staticmethod
    def cleanup(path: str | None) -> None:
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass
