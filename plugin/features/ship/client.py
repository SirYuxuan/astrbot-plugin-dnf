from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class ShipBonus:
    text: str
    value: float
    unit_id: int | None = None


@dataclass(frozen=True)
class ShipSkillBonus:
    skill_name: str
    skill_type_id: int
    bonuses: tuple[ShipBonus, ...]


@dataclass(frozen=True)
class ShipInfo:
    type_id: int
    name: str
    name_en: str
    description: str
    high_slots: int
    mid_slots: int
    low_slots: int
    rig_slots: int
    turret_hardpoints: int
    launcher_hardpoints: int
    role_bonuses: tuple[ShipBonus, ...]
    skill_bonuses: tuple[ShipSkillBonus, ...]
    image_data_url: str


class ShipClient:
    DEFAULT_INFO_URL = "https://admin-api.oofo.cc/game/eve/public/ships/info"
    DEFAULT_IMAGE_URL = "https://admin-api.oofo.cc/game/eve/assets/types/{type_id}/icon"

    def __init__(
        self,
        *,
        info_url: str = DEFAULT_INFO_URL,
        image_url: str = DEFAULT_IMAGE_URL,
        timeout: int = 15,
    ) -> None:
        self.info_url = info_url
        self.image_url = image_url
        self.timeout = max(1, timeout)

    def query(self, name: str) -> ShipInfo:
        response = requests.get(self.info_url, params={"name": name}, timeout=self.timeout)
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("舰船资料接口返回了无效数据")
        if payload.get("code") != 0:
            raise ValueError(str(payload.get("message") or "舰船资料查询失败"))
        response.raise_for_status()
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("舰船资料接口未返回舰船数据")

        type_id = self._positive_int(data.get("typeId"))
        if type_id is None:
            raise ValueError("舰船资料缺少 typeId")
        slots = data.get("slots") if isinstance(data.get("slots"), dict) else {}
        hardpoints = data.get("hardpoints") if isinstance(data.get("hardpoints"), dict) else {}
        return ShipInfo(
            type_id=type_id,
            name=str(data.get("name") or name).strip(),
            name_en=str(data.get("nameEn") or "").strip(),
            description=str(data.get("description") or "").strip(),
            high_slots=self._nonnegative_int(slots.get("high")),
            mid_slots=self._nonnegative_int(slots.get("mid")),
            low_slots=self._nonnegative_int(slots.get("low")),
            rig_slots=self._nonnegative_int(slots.get("rig")),
            turret_hardpoints=self._nonnegative_int(hardpoints.get("turret")),
            launcher_hardpoints=self._nonnegative_int(hardpoints.get("launcher")),
            role_bonuses=self._bonuses(data.get("roleBonuses")),
            skill_bonuses=self._skill_bonuses(data.get("skillBonuses")),
            image_data_url=self._fetch_image(type_id),
        )

    def _fetch_image(self, type_id: int) -> str:
        url = self.image_url.format(type_id=type_id)
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "image/png").split(";", 1)[0]
        if not content_type.startswith("image/"):
            raise ValueError("舰船图片接口未返回图片")
        encoded = base64.b64encode(response.content).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    @classmethod
    def _bonuses(cls, value: Any) -> tuple[ShipBonus, ...]:
        if not isinstance(value, list):
            return ()
        bonuses: list[ShipBonus] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            bonuses.append(
                ShipBonus(
                    text=text,
                    value=cls._number(item.get("value")),
                    unit_id=cls._optional_int(item.get("unitId")),
                )
            )
        return tuple(bonuses)

    @classmethod
    def _skill_bonuses(cls, value: Any) -> tuple[ShipSkillBonus, ...]:
        if not isinstance(value, list):
            return ()
        groups: list[ShipSkillBonus] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            skill_name = str(item.get("skillName") or "").strip()
            bonuses = cls._bonuses(item.get("bonuses"))
            if not skill_name or not bonuses:
                continue
            groups.append(
                ShipSkillBonus(
                    skill_name=skill_name,
                    skill_type_id=cls._nonnegative_int(item.get("skillTypeId")),
                    bonuses=bonuses,
                )
            )
        return tuple(groups)

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _positive_int(cls, value: Any) -> int | None:
        result = cls._optional_int(value)
        return result if result is not None and result > 0 else None

    @classmethod
    def _nonnegative_int(cls, value: Any) -> int:
        result = cls._optional_int(value)
        return max(0, result or 0)
