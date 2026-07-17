import os
import tempfile
import time
from urllib.parse import urlparse

import requests

from astrbot.api import logger


class MusicGenerator:
    def __init__(self, config: dict):
        self.enabled = bool(config.get("enabled"))
        self.endpoint = str(config.get("endpoint") or "").strip()
        self.api_key = str(config.get("api_key") or "").strip()
        self.timeout_seconds = int(config.get("timeout_seconds") or 180)
        self.poll_interval_seconds = int(config.get("poll_interval_seconds") or 2)

    def is_ready(self) -> bool:
        return self.enabled and bool(self.endpoint and self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str, lyrics: str) -> tuple[str | None, str | None, str | None]:
        if not self.enabled:
            return None, None, "写歌功能未启用"
        if not self.endpoint or not self.api_key:
            return None, None, "写歌配置不完整，请配置 endpoint 和 api_key"

        payload = {"prompt": prompt}
        if lyrics:
            payload["lyrics"] = lyrics
        else:
            payload["lyrics_optimizer"] = True
        logger.info(f"写歌请求参数: endpoint={self.endpoint}, payload={payload}")
        try:
            response = requests.post(self.endpoint, headers=self._headers(), json=payload, timeout=self.timeout_seconds)
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"写歌请求失败: {e}")
            return None, None, f"网络请求失败: {e}"
        except Exception as e:
            logger.error(f"写歌响应解析失败: {e}")
            return None, None, f"响应解析失败: {e}"

        if response.status_code >= 400:
            return None, None, f"写歌提交失败: {data}"
        if isinstance(data, dict) and data.get("request_id"):
            return self._wait_result(str(data["request_id"]), str(data.get("status_url") or ""), str(data.get("response_url") or ""))
        return self._save_audio_from_data(data)

    def _wait_result(self, request_id: str, status_url: str, result_url: str) -> tuple[str | None, str | None, str | None]:
        base = self.endpoint.rstrip("/")
        status_url = status_url or f"{base}/requests/{request_id}/status"
        result_url = result_url or f"{base}/requests/{request_id}"
        deadline = time.time() + self.timeout_seconds

        while time.time() < deadline:
            try:
                response = requests.get(status_url, headers=self._headers(), timeout=self.timeout_seconds)
                data = response.json()
            except requests.RequestException as e:
                logger.error(f"写歌状态查询失败: {e}")
                return None, None, f"状态查询失败: {e}"
            except Exception as e:
                logger.error(f"写歌状态解析失败: {e}")
                return None, None, f"状态解析失败: {e}"

            status = str(data.get("status", "")).upper() if isinstance(data, dict) else ""
            if status in ("COMPLETED", "COMPLETED_WITH_LOGS"):
                return self._fetch_result(result_url)
            if status in ("FAILED", "ERROR", "CANCELLED"):
                return None, None, f"写歌失败: {data}"
            time.sleep(max(1, self.poll_interval_seconds))

        return None, None, "写歌任务超时"

    def _fetch_result(self, result_url: str) -> tuple[str | None, str | None, str | None]:
        try:
            response = requests.get(result_url, headers=self._headers(), timeout=self.timeout_seconds)
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"写歌结果获取失败: {e}")
            return None, None, f"结果获取失败: {e}"
        except Exception as e:
            logger.error(f"写歌结果解析失败: {e}")
            return None, None, f"结果解析失败: {e}"

        if response.status_code >= 400:
            return None, None, f"写歌结果获取失败: {data}"
        return self._save_audio_from_data(data)

    def _save_audio_from_data(self, data) -> tuple[str | None, str | None, str | None]:
        if not isinstance(data, dict):
            return None, None, "API 未返回音频数据"
        audio = data.get("audio")
        audio_url = audio.get("url") if isinstance(audio, dict) else ""
        if not audio_url:
            return None, None, "API 未返回音频 URL"
        return self._save_url_audio(str(audio_url))

    def _save_url_audio(self, audio_url: str) -> tuple[str | None, str | None, str | None]:
        try:
            response = requests.get(audio_url, timeout=self.timeout_seconds)
            response.raise_for_status()
            suffix = os.path.splitext(urlparse(audio_url).path)[1] or ".mp3"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.write(response.content)
            tmp.close()
            return tmp.name, audio_url, None
        except requests.RequestException as e:
            logger.error(f"下载生成音频失败: {e}")
            return None, audio_url, f"下载生成音频失败: {e}"
        except Exception as e:
            logger.error(f"保存生成音频失败: {e}")
            return None, audio_url, f"保存音频失败: {e}"
