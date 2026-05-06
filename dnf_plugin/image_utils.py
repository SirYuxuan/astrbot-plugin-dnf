import base64
import tempfile

import requests

from astrbot.api import logger


class ImageGenerator:
    def __init__(self, config: dict):
        self.enabled = bool(config.get("enabled"))
        self.endpoint = str(config.get("endpoint") or "").strip()
        self.api_key = str(config.get("api_key") or "").strip()
        self.auth_header = str(config.get("auth_header") or "api-key").strip()
        self.size = str(config.get("size") or "1024x1024")
        self.quality = str(config.get("quality") or "low")
        self.output_format = str(config.get("output_format") or "png")
        self.timeout_seconds = int(config.get("timeout_seconds") or 180)

    def is_ready(self) -> bool:
        return self.enabled and bool(self.endpoint and self.api_key)

    def generate(self, prompt: str) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, "图片生成功能未启用"
        if not self.endpoint or not self.api_key:
            return None, "图片生成配置不完整，请配置 endpoint 和 api_key"

        headers = {"Content-Type": "application/json"}
        if self.auth_header.lower() == "authorization":
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers[self.auth_header] = self.api_key

        payload = {
            "prompt": prompt,
            "size": self.size,
            "quality": self.quality,
            "output_format": self.output_format,
            "n": 1,
        }

        try:
            response = requests.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout_seconds)
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"图片生成请求失败: {e}")
            return None, f"网络请求失败: {e}"
        except Exception as e:
            logger.error(f"图片生成响应解析失败: {e}")
            return None, f"响应解析失败: {e}"

        if response.status_code != 200:
            error = data.get("error", {}).get("message", str(data)) if isinstance(data, dict) else str(data)
            logger.error(f"图片生成 API 返回错误: {error}")
            return None, f"图片生成失败: {error}"

        b64 = ""
        if isinstance(data, dict):
            b64 = ((data.get("data") or [{}])[0] or {}).get("b64_json", "")
        if not b64:
            return None, "API 未返回图片数据"

        try:
            image_bytes = base64.b64decode(b64)
            tmp = tempfile.NamedTemporaryFile(suffix=f".{self.output_format}", delete=False)
            tmp.write(image_bytes)
            tmp.close()
            return tmp.name, None
        except Exception as e:
            logger.error(f"保存生成图片失败: {e}")
            return None, f"保存图片失败: {e}"
