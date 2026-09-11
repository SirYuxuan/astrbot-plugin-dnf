from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import requests

from .catalog import EveCatalog, EveType

MANIFEST_URL = "https://developers.eveonline.com/static-data/tranquility/latest.jsonl"
ARCHIVE_URL = (
    "https://developers.eveonline.com/static-data/tranquility/"
    "eve-online-static-data-{build}-jsonl.zip"
)


class SdeUpdater:
    def __init__(self, catalog: EveCatalog, timeout: int = 180, user_agent: str = ""):
        self.catalog = catalog
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent} if user_agent else {}

    def latest_build(self) -> int:
        response = requests.get(MANIFEST_URL, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        for line in response.text.splitlines():
            record = json.loads(line)
            if record.get("_key") == "sde":
                return int(record["buildNumber"])
        raise ValueError("CCP SDE 清单中没有 sde 版本")

    def update(self, force: bool = False) -> tuple[int, int, bool]:
        build = self.latest_build()
        status = self.catalog.status()
        if not force and str(status["build"] or "") == str(build) and status["count"]:
            return build, int(status["count"]), False
        archive = self._download(build)
        try:
            items = self._read_types(archive)
            count = self.catalog.replace_types(items, build)
        finally:
            archive.unlink(missing_ok=True)
        return build, count, True

    def _download(self, build: int) -> Path:
        temporary: Path | None = None
        try:
            with requests.get(
                ARCHIVE_URL.format(build=build),
                headers=self.headers,
                timeout=self.timeout,
                stream=True,
            ) as response:
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(
                    dir=self.catalog.path.parent, prefix="sde-", suffix=".zip", delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            stream.write(chunk)
            return temporary
        except Exception:
            if temporary:
                temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _read_types(archive: Path) -> list[EveType]:
        result: list[EveType] = []
        with zipfile.ZipFile(archive) as bundle:
            member = next(
                (name for name in bundle.namelist() if PurePosixPath(name).name == "types.jsonl"),
                None,
            )
            if not member:
                raise ValueError("SDE 压缩包中缺少 types.jsonl")
            with bundle.open(member) as source:
                for raw_line in source:
                    record = json.loads(raw_line)
                    names = record.get("name") or {}
                    name_en = str(names.get("en") or "").strip()
                    if not name_en:
                        continue
                    result.append(
                        EveType(
                            type_id=int(record["_key"]),
                            name_en=name_en,
                            name_zh=str(names.get("zh") or "").strip() or None,
                            group_id=record.get("groupID"),
                            market_group_id=record.get("marketGroupID"),
                            published=bool(record.get("published", False)),
                        )
                    )
        return result
