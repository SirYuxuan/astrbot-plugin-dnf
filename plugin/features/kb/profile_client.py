"""Public KBINFO data loader with bounded sampling and a short cache."""

import copy
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

logger = logging.getLogger(__name__)


class KbProfileClient:
    def __init__(self, client):
        self.client = client
        self._cache = {}
        self._lock = threading.Lock()

    def _get(self, url, expected, **params):
        response = requests.get(
            url, params=params or None, headers=self.client.headers, timeout=self.client.timeout
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, expected) or (isinstance(data, dict) and data.get("error")):
            raise ValueError("KBINFO 上游数据格式无效")
        return data

    def query(self, name):
        # One profile build at a time prevents duplicate requests for the same report.
        with self._lock:
            key = " ".join(name.split()).casefold()
            cached = self._cache.get(key)
            if cached and cached[0] > time.monotonic():
                return copy.deepcopy(cached[1])
            identity = self.client.resolve_character(name)
            if identity is None:
                return None
            cid, _ = identity
            character = self._get(f"https://esi.evetech.net/latest/characters/{cid}/", dict)
            stats_url = self.client.zkill_stats_url.format(character_id=cid).replace("/kills/", "/")
            stats = self._get(stats_url, dict)
            warnings = []
            try:
                history = self._get(
                    f"https://esi.evetech.net/latest/characters/{cid}/corporationhistory/", list
                )
                history = [
                    r
                    for r in history
                    if isinstance(r, dict) and r.get("corporation_id") and r.get("start_date")
                ]
            except (requests.RequestException, ValueError):
                history = []
                warnings.append("军团历史")
            summaries = {}
            for page in range(1, 4 + 1):
                url = self.client.zkill_recent_url.format(character_id=cid, activity=f"page/{page}")
                try:
                    batch = self._get(url, list)
                except (requests.RequestException, ValueError):
                    warnings.append("近期 KM 抽样不完整")
                    break
                added = 0
                for row in batch:
                    if isinstance(row, dict) and self.client._positive_int(row.get("killmail_id")):
                        kid = int(row["killmail_id"])
                        if kid not in summaries:
                            summaries[kid] = row
                            added += 1
                if len(summaries) >= 400 or len(batch) < 200 or not added:
                    break

            def detail(row):
                if isinstance(row.get("victim"), dict) and isinstance(row.get("attackers"), list):
                    return row
                kill_hash = (row.get("zkb") or {}).get("hash")
                if not kill_hash:
                    return None
                try:
                    data = self._get(
                        self.client.esi_killmail_url.format(
                            killmail_id=row["killmail_id"], killmail_hash=kill_hash
                        ),
                        dict,
                    )
                    return {**data, "killmail_id": row["killmail_id"], "zkb": row.get("zkb", {})}
                except (requests.RequestException, ValueError):
                    return None

            rows = sorted(summaries.values(), key=lambda r: int(r["killmail_id"]), reverse=True)[
                :400
            ]
            with ThreadPoolExecutor(max_workers=4) as pool:
                hydrated = list(pool.map(detail, rows))
            records = [
                r
                for r in hydrated
                if r
                and isinstance(r.get("victim"), dict)
                and r["victim"].get("ship_type_id")
                and isinstance(r.get("attackers"), list)
                and r.get("killmail_time")
                and r.get("solar_system_id")
            ]
            records.sort(key=lambda r: r["killmail_time"], reverse=True)
            if len(records) < len(rows):
                warnings.append("部分 KM 详情")
            ids = [character.get("corporation_id", 0), character.get("alliance_id", 0)]
            ids += [r["corporation_id"] for r in history]
            ids += [r["solar_system_id"] for r in records]
            try:
                names = self.client.names(ids)
            except (requests.RequestException, ValueError):
                names = {}
                warnings.append("部分名称")
            result = {
                "identity": identity,
                "character": character,
                "stats": stats,
                "history": history,
                "records": records,
                "names": names,
                "warnings": warnings,
            }
            if len(self._cache) >= 64:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic() + self.client.cache_seconds, result)
            return copy.deepcopy(result)
