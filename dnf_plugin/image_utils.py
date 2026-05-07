import base64
import mimetypes
import os
import tempfile
import time
from urllib.parse import urlparse

import requests

from astrbot.api import logger


class ImageGenerator:
    def __init__(self, config: dict):
        self.enabled = bool(config.get("enabled"))
        self.text_provider = str(config.get("text_provider") or "microsoft").strip()
        self.edit_provider = str(config.get("edit_provider") or "microsoft").strip()
        self.model = str(config.get("model") or "").strip()
        self.size = str(config.get("size") or "1024x1024")
        self.quality = str(config.get("quality") or "").strip()
        self.output_format = str(config.get("output_format") or "png")
        self.output_compression = config.get("output_compression")
        self.num_images = int(config.get("num_images") or 1)
        self.edit_prompt_prefix = str(config.get("edit_prompt_prefix") or "").strip()
        self.timeout_seconds = int(config.get("timeout_seconds") or 180)

        self.microsoft_endpoint = str(config.get("microsoft_endpoint") or config.get("endpoint") or "").strip()
        self.microsoft_edit_endpoint = str(config.get("microsoft_edit_endpoint") or config.get("edit_endpoint") or "").strip()
        self.microsoft_api_key = str(config.get("microsoft_api_key") or config.get("api_key") or "").strip()
        self.microsoft_auth_header = str(config.get("microsoft_auth_header") or config.get("auth_header") or "api-key").strip()

        self.fal_text_endpoint = str(config.get("fal_text_endpoint") or "").strip()
        self.fal_edit_endpoint = str(config.get("fal_edit_endpoint") or config.get("fal_endpoint") or "").strip()
        self.fal_key = str(config.get("fal_key") or "").strip()
        self.fal_poll_interval_seconds = int(config.get("fal_poll_interval_seconds") or 2)
        self.fal_timeout_seconds = int(config.get("fal_timeout_seconds") or 180)

    def can_generate(self) -> bool:
        if not self.enabled:
            return False
        if self.text_provider == "fal":
            return bool(self.fal_text_endpoint and self.fal_key)
        return bool(self.microsoft_endpoint and self.microsoft_api_key)

    def can_edit(self) -> bool:
        if not self.enabled:
            return False
        if self.edit_provider == "fal":
            return bool(self.fal_edit_endpoint and self.fal_key)
        return bool((self.microsoft_edit_endpoint or self.microsoft_endpoint) and self.microsoft_api_key)

    def is_ready(self) -> bool:
        return self.can_generate()

    def _microsoft_headers(self, content_type: str | None = "application/json") -> dict:
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        if self.microsoft_auth_header.lower() == "authorization":
            headers["Authorization"] = f"Bearer {self.microsoft_api_key}"
        else:
            headers[self.microsoft_auth_header] = self.microsoft_api_key
        return headers

    def _fal_headers(self) -> dict:
        return {
            "Authorization": f"Key {self.fal_key}",
            "Content-Type": "application/json",
        }

    def _resolve_microsoft_edit_endpoint(self) -> str:
        if self.microsoft_edit_endpoint:
            return self.microsoft_edit_endpoint
        if "/images/generations" in self.microsoft_endpoint:
            return self.microsoft_endpoint.replace("/images/generations", "/images/edits", 1)
        return self.microsoft_endpoint

    def _prepare_image_file(self, image: str) -> tuple[str | None, bool, str | None]:
        if not image:
            return None, False, "未找到可用的输入图片"
        if image.startswith("file:///"):
            image = image[8:]
        if os.path.exists(image):
            return image, False, None
        if image.startswith("base64://"):
            try:
                image_bytes = base64.b64decode(image.removeprefix("base64://"))
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.write(image_bytes)
                tmp.close()
                return tmp.name, True, None
            except Exception as e:
                logger.error(f"解析输入图片 base64 失败: {e}")
                return None, False, f"解析输入图片失败: {e}"
        if image.startswith("http://") or image.startswith("https://"):
            try:
                response = requests.get(image, timeout=self.timeout_seconds)
                response.raise_for_status()
                suffix = os.path.splitext(urlparse(image).path)[1] or ".png"
                tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                tmp.write(response.content)
                tmp.close()
                return tmp.name, True, None
            except requests.RequestException as e:
                logger.error(f"下载输入图片失败: {e}")
                return None, False, f"下载输入图片失败: {e}"
        return None, False, "未找到可用的输入图片"

    def _save_b64_image(self, b64: str) -> tuple[str | None, str | None]:
        try:
            image_bytes = base64.b64decode(b64)
            tmp = tempfile.NamedTemporaryFile(suffix=f".{self.output_format}", delete=False)
            tmp.write(image_bytes)
            tmp.close()
            return tmp.name, None
        except Exception as e:
            logger.error(f"保存生成图片失败: {e}")
            return None, f"保存图片失败: {e}"

    def _save_url_image(self, image_url: str) -> tuple[str | None, str | None]:
        try:
            response = requests.get(image_url, timeout=self.timeout_seconds)
            response.raise_for_status()
            suffix = os.path.splitext(urlparse(image_url).path)[1] or f".{self.output_format}"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.write(response.content)
            tmp.close()
            return tmp.name, None
        except requests.RequestException as e:
            logger.error(f"下载生成图片失败: {e}")
            return None, f"下载生成图片失败: {e}"
        except Exception as e:
            logger.error(f"保存生成图片失败: {e}")
            return None, f"保存图片失败: {e}"

    def _extract_image_url(self, data: dict) -> str:
        for key in ("images", "data"):
            items = data.get(key)
            if isinstance(items, list) and items:
                item = items[0] or {}
                if isinstance(item, dict) and item.get("url"):
                    return str(item["url"])
        if data.get("image", {}).get("url"):
            return str(data["image"]["url"])
        return ""

    def _read_image_response(self, response: requests.Response) -> tuple[str | None, str | None]:
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"图片生成响应解析失败: {e}")
            text = response.text[:300] if getattr(response, "text", "") else ""
            if response.status_code != 200:
                return None, f"图片生成失败: HTTP {response.status_code} {text}"
            return None, f"响应解析失败: {e}"

        if response.status_code != 200:
            error = str(data)
            if isinstance(data, dict):
                raw_error = data.get("error")
                if isinstance(raw_error, dict):
                    error = raw_error.get("message", str(raw_error))
                elif raw_error:
                    error = str(raw_error)
                elif data.get("message"):
                    error = str(data.get("message"))
            logger.error(f"图片生成 API 返回错误({response.status_code}): {error}")
            return None, f"图片生成失败: {error}"

        return self._save_image_from_data(data)

    def _save_image_from_data(self, data) -> tuple[str | None, str | None]:
        if not isinstance(data, dict):
            return None, "API 未返回图片数据"
        item = ((data.get("data") or [{}])[0] or {})
        b64 = item.get("b64_json", "") if isinstance(item, dict) else ""
        if b64:
            return self._save_b64_image(b64)
        image_url = self._extract_image_url(data)
        if image_url:
            return self._save_url_image(image_url)
        return None, "API 未返回图片数据"

    def _log_request(self, action: str, endpoint: str, payload: dict, image_path: str | None = None) -> None:
        safe_payload = dict(payload)
        image_info = ""
        if image_path:
            try:
                image_info = (
                    f", image_name={os.path.basename(image_path)}, "
                    f"image_size={os.path.getsize(image_path)}, "
                    f"image_mime={mimetypes.guess_type(image_path)[0] or 'image/png'}"
                )
            except Exception as e:
                image_info = f", image_info_error={e}"
        logger.info(f"{action}请求参数: endpoint={endpoint}, payload={safe_payload}{image_info}")

    def _microsoft_payload(self, prompt: str) -> dict:
        payload = {
            "prompt": prompt,
            "size": self.size,
            "output_format": self.output_format,
            "n": self.num_images,
        }
        if self.model:
            payload["model"] = self.model
        if self.quality:
            payload["quality"] = self.quality
        if self.output_compression not in (None, ""):
            payload["output_compression"] = int(self.output_compression)
        return payload

    def _fal_image_size(self, fallback: str = "auto"):
        if self.size and "x" in self.size:
            width, height = self.size.lower().split("x", 1)
            try:
                return {"width": int(width), "height": int(height)}
            except ValueError:
                return fallback
        return self.size or fallback

    def generate(self, prompt: str) -> tuple[str | None, str | None]:
        if self.text_provider == "fal":
            return self._generate_with_fal(prompt)
        return self._generate_with_microsoft(prompt)

    def _generate_with_microsoft(self, prompt: str) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, "图片生成功能未启用"
        if not self.microsoft_endpoint or not self.microsoft_api_key:
            return None, "微软图片生成配置不完整，请配置 microsoft_endpoint 和 microsoft_api_key"

        payload = self._microsoft_payload(prompt)
        self._log_request("画图", self.microsoft_endpoint, payload)
        try:
            response = requests.post(
                self.microsoft_endpoint,
                headers=self._microsoft_headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as e:
            logger.error(f"图片生成请求失败: {e}")
            return None, f"网络请求失败: {e}"
        return self._read_image_response(response)

    def _generate_with_fal(self, prompt: str) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, "图片生成功能未启用"
        if not self.fal_text_endpoint or not self.fal_key:
            return None, "FAL 文生图配置不完整，请配置 fal_text_endpoint 和 fal_key"

        payload = {
            "prompt": prompt,
            "quality": self.quality or "medium",
            "image_size": self._fal_image_size("square"),
            "num_images": self.num_images,
            "output_format": self.output_format,
        }
        self._log_request("FAL画图", self.fal_text_endpoint, payload)
        try:
            response = requests.post(
                self.fal_text_endpoint,
                headers=self._fal_headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as e:
            logger.error(f"FAL 文生图请求失败: {e}")
            return None, f"网络请求失败: {e}"
        return self._read_fal_response(self.fal_text_endpoint, response)

    def edit(self, image_path: str, prompt: str) -> tuple[str | None, str | None]:
        if self.edit_provider == "fal":
            return self._edit_with_fal(image_path, prompt)
        return self._edit_with_microsoft(image_path, prompt)

    def _edit_with_microsoft(self, image_path: str, prompt: str) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, "图片生成功能未启用"
        if not self.microsoft_api_key or not (self.microsoft_edit_endpoint or self.microsoft_endpoint):
            return None, "微软图生图配置不完整，请配置 microsoft_edit_endpoint 和 microsoft_api_key"

        input_path, should_cleanup, prepare_error = self._prepare_image_file(image_path)
        if prepare_error or not input_path:
            return None, prepare_error

        payload = self._microsoft_payload(f"{self.edit_prompt_prefix}{prompt}" if self.edit_prompt_prefix else prompt)
        endpoint = self._resolve_microsoft_edit_endpoint()
        mime_type = mimetypes.guess_type(input_path)[0] or "image/png"
        self._log_request("图生图", endpoint, payload, input_path)
        try:
            with open(input_path, "rb") as image_file:
                response = requests.post(
                    endpoint,
                    headers=self._microsoft_headers(None),
                    data=payload,
                    files={"image": (os.path.basename(input_path), image_file, mime_type)},
                    timeout=self.timeout_seconds,
                )
        except requests.RequestException as e:
            logger.error(f"图生图请求失败: {e}")
            return None, f"网络请求失败: {e}"
        except Exception as e:
            logger.error(f"读取输入图片失败: {e}")
            return None, f"读取输入图片失败: {e}"
        finally:
            if should_cleanup and input_path:
                try:
                    os.unlink(input_path)
                except Exception:
                    pass
        return self._read_image_response(response)

    def _edit_with_fal(self, image_url: str, prompt: str) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, "图片生成功能未启用"
        if not self.fal_edit_endpoint or not self.fal_key:
            return None, "FAL 图生图配置不完整，请配置 fal_edit_endpoint 和 fal_key"
        if not image_url.startswith(("http://", "https://")):
            return None, "FAL 图生图需要公网图片 URL"

        payload = {
            "prompt": prompt,
            "quality": self.quality or "medium",
            "image_size": "auto",
            "image_urls": [image_url],
            "num_images": self.num_images,
            "output_format": self.output_format,
        }
        self._log_request("FAL图生图", self.fal_edit_endpoint, payload)
        try:
            response = requests.post(
                self.fal_edit_endpoint,
                headers=self._fal_headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as e:
            logger.error(f"FAL 图生图请求失败: {e}")
            return None, f"网络请求失败: {e}"
        return self._read_fal_response(self.fal_edit_endpoint, response)

    def _read_fal_response(self, endpoint: str, response: requests.Response) -> tuple[str | None, str | None]:
        try:
            data = response.json()
        except Exception as e:
            logger.error(f"FAL 响应解析失败: {e}")
            text = response.text[:300] if getattr(response, "text", "") else ""
            return None, f"FAL 响应解析失败: HTTP {response.status_code} {text}"

        if response.status_code >= 400:
            return None, f"FAL 请求失败: {data}"
        if isinstance(data, dict) and data.get("request_id"):
            return self._wait_fal_result(
                str(data["request_id"]),
                str(data.get("status_url") or ""),
                str(data.get("response_url") or ""),
                endpoint,
            )
        return self._save_image_from_data(data)

    def _wait_fal_result(
        self,
        request_id: str,
        status_url: str,
        result_url: str,
        endpoint: str,
    ) -> tuple[str | None, str | None]:
        base = endpoint.rstrip("/")
        status_url = status_url or f"{base}/requests/{request_id}/status"
        result_url = result_url or f"{base}/requests/{request_id}"
        deadline = time.time() + self.fal_timeout_seconds

        while time.time() < deadline:
            try:
                status_response = requests.get(status_url, headers=self._fal_headers(), timeout=self.timeout_seconds)
                status_data = status_response.json()
            except requests.RequestException as e:
                logger.error(f"FAL 状态查询失败: {e}")
                return None, f"FAL 状态查询失败: {e}"
            except Exception as e:
                logger.error(f"FAL 状态解析失败: {e}")
                return None, f"FAL 状态解析失败: {e}"

            status = str(status_data.get("status", "")).upper() if isinstance(status_data, dict) else ""
            if status in ("COMPLETED", "COMPLETED_WITH_LOGS"):
                return self._fetch_fal_result(result_url)
            if status in ("FAILED", "ERROR", "CANCELLED"):
                return None, f"FAL 任务失败: {status_data}"
            time.sleep(max(1, self.fal_poll_interval_seconds))

        return None, "FAL 任务超时"

    def _fetch_fal_result(self, result_url: str) -> tuple[str | None, str | None]:
        try:
            response = requests.get(result_url, headers=self._fal_headers(), timeout=self.timeout_seconds)
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"FAL 结果获取失败: {e}")
            return None, f"FAL 结果获取失败: {e}"
        except Exception as e:
            logger.error(f"FAL 结果解析失败: {e}")
            return None, f"FAL 结果解析失败: {e}"

        if response.status_code >= 400:
            return None, f"FAL 结果获取失败: {data}"
        return self._save_image_from_data(data)
