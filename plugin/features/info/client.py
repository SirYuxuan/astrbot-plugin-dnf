from ..rat.client import RatClient


class InfoClient(RatClient):
    """按 QQ 查询 EVE 用户信息。"""

    DEFAULT_URL = "https://admin-api.oofo.cc/game/eve/public/users/by-qq/{qq}/info"
