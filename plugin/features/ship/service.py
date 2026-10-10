from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from .client import ShipClient
from .renderer import ShipCardRenderer


@dataclass(frozen=True)
class ShipReply:
    text: str
    html: str | None = None


class ShipFeature:
    def __init__(self, client: ShipClient, renderer: ShipCardRenderer | None = None) -> None:
        self.client = client
        self.renderer = renderer or ShipCardRenderer()

    async def query(self, command: str) -> ShipReply:
        name = re.sub(r"^/?(?:ship|舰船)(?:\s+|$)", "", command.strip(), count=1).strip()
        if not name:
            return ShipReply("用法：/ship 乌鸦级")
        try:
            ship = await asyncio.to_thread(self.client.query, name)
        except ValueError as error:
            return ShipReply(str(error))
        return ShipReply(
            text=f"{ship.name} ({ship.name_en}) 舰船资料",
            html=self.renderer.render(ship),
        )
