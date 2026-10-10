from __future__ import annotations

import datetime as dt
import re


class TimerFeature:
    _COMMAND = re.compile(r"^/?timer(?:\s+|$)", re.IGNORECASE)
    _UNIT = re.compile(
        r"(\d+)\s*(天|日|小时|时|分钟|分|days?|d|hours?|hrs?|h|minutes?|mins?|m)",
        re.IGNORECASE,
    )
    _SEPARATOR = re.compile(r"[.。\s:：/／,，_-]+")
    _IGNORABLE = re.compile(r"[\s,，、]+")
    _BEIJING = dt.timezone(dt.timedelta(hours=8))

    async def query(self, message: str) -> str:
        value = self._COMMAND.sub("", message.strip(), count=1).strip()
        duration = self.parse_duration(value)
        if duration is None:
            return "❌ 参数格式不正确\n示例：/timer 2天2小时5分、/timer 2.2.5、/timer 2 2 5"
        return self.format_deadline(duration)

    @classmethod
    def parse_duration(cls, value: str) -> dt.timedelta | None:
        if not value:
            return None

        parts = cls._SEPARATOR.split(value.strip())
        if 1 <= len(parts) <= 3 and all(part.isdigit() for part in parts):
            numbers = [int(part) for part in parts]
            if len(numbers) == 1:
                return cls._duration(0, 0, numbers[0])
            if len(numbers) == 2:
                return cls._duration(0, numbers[0], numbers[1])
            return cls._duration(*numbers)

        values = {"days": 0, "hours": 0, "minutes": 0}
        seen: set[str] = set()
        position = 0
        matched = False
        for match in cls._UNIT.finditer(value):
            if not cls._IGNORABLE.fullmatch(value[position : match.start()] or " "):
                return None
            matched = True
            unit = match.group(2).casefold()
            if unit in {"天", "日", "d", "day", "days"}:
                key = "days"
            elif unit in {"小时", "时", "h", "hr", "hrs", "hour", "hours"}:
                key = "hours"
            else:
                key = "minutes"
            if key in seen:
                return None
            seen.add(key)
            values[key] = int(match.group(1))
            position = match.end()
        if not matched or not cls._IGNORABLE.fullmatch(value[position:] or " "):
            return None
        return cls._duration(values["days"], values["hours"], values["minutes"])

    @staticmethod
    def _duration(days: int, hours: int, minutes: int) -> dt.timedelta | None:
        total_minutes = days * 24 * 60 + hours * 60 + minutes
        if total_minutes <= 0 or total_minutes > 36500 * 24 * 60:
            return None
        return dt.timedelta(minutes=total_minutes)

    @classmethod
    def format_deadline(cls, duration: dt.timedelta, now: dt.datetime | None = None) -> str:
        eve_now = now or dt.datetime.now(dt.timezone.utc)
        if eve_now.tzinfo is None:
            eve_now = eve_now.replace(tzinfo=dt.timezone.utc)
        eve_deadline = eve_now.astimezone(dt.timezone.utc) + duration
        beijing_deadline = eve_deadline.astimezone(cls._BEIJING)
        return f"EVE时间：{eve_deadline:%m-%d %H:%M}\n北京时间：{beijing_deadline:%m-%d %H:%M}"
