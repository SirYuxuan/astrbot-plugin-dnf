from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


def normalize_name(value: str) -> str:
    """保留型号和数字，只统一宽度、大小写与空白。"""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@dataclass(frozen=True)
class EveType:
    type_id: int
    name_en: str
    name_zh: str | None
    group_id: int | None = None
    market_group_id: int | None = None
    published: bool = True

    @property
    def display_name(self) -> str:
        if self.name_zh and self.name_zh != self.name_en:
            return f"{self.name_zh} {self.name_en}"
        return self.name_zh or self.name_en or str(self.type_id)


class EveCatalog:
    """SDE 派生名称索引，以及不随 SDE 更新删除的用户别名。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS types (
                    type_id INTEGER PRIMARY KEY,
                    name_en TEXT NOT NULL,
                    name_zh TEXT,
                    group_id INTEGER,
                    market_group_id INTEGER,
                    published INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS type_names (
                    type_id INTEGER NOT NULL,
                    language TEXT NOT NULL,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    PRIMARY KEY (type_id, language),
                    FOREIGN KEY (type_id) REFERENCES types(type_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_type_names_normalized
                    ON type_names(normalized_name);
                CREATE TABLE IF NOT EXISTS aliases (
                    normalized_alias TEXT PRIMARY KEY,
                    alias TEXT NOT NULL,
                    type_id INTEGER NOT NULL,
                    created_by TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def replace_types(self, items: Iterable[EveType], build_number: int) -> int:
        rows = list(items)
        if not rows:
            raise ValueError("SDE 中没有物品类型数据")
        names: list[tuple[int, str, str, str]] = []
        for item in rows:
            names.append((item.type_id, "en", item.name_en, normalize_name(item.name_en)))
            if item.name_zh:
                names.append((item.type_id, "zh", item.name_zh, normalize_name(item.name_zh)))
        with self._connect() as db:
            db.execute("DELETE FROM type_names")
            db.execute("DELETE FROM types")
            db.executemany(
                """INSERT INTO types
                   (type_id, name_en, name_zh, group_id, market_group_id, published)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        item.type_id,
                        item.name_en,
                        item.name_zh,
                        item.group_id,
                        item.market_group_id,
                        int(item.published),
                    )
                    for item in rows
                ],
            )
            db.executemany(
                """INSERT INTO type_names(type_id, language, name, normalized_name)
                   VALUES (?, ?, ?, ?)""",
                names,
            )
            db.execute(
                """INSERT INTO metadata(key, value) VALUES ('sde_build', ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (str(build_number),),
            )
            db.execute(
                """INSERT INTO metadata(key, value) VALUES ('sde_updated_at', CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value"""
            )
        return len(rows)

    def status(self) -> dict[str, str | int | None]:
        with self._connect() as db:
            count = int(db.execute("SELECT COUNT(*) FROM types").fetchone()[0])
            metadata = dict(db.execute("SELECT key, value FROM metadata").fetchall())
        return {
            "count": count,
            "build": metadata.get("sde_build"),
            "updated_at": metadata.get("sde_updated_at"),
        }

    def get_type(self, type_id: int) -> EveType | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM types WHERE type_id = ?", (type_id,)).fetchone()
        return self._to_type(row) if row else None

    def exact(self, query: str) -> EveType | None:
        return self.alias(query) or self.official_exact(query)

    def alias(self, query: str) -> EveType | None:
        normalized = normalize_name(query)
        with self._connect() as db:
            alias = db.execute(
                "SELECT type_id FROM aliases WHERE normalized_alias = ?", (normalized,)
            ).fetchone()
            if alias:
                row = db.execute("SELECT * FROM types WHERE type_id = ?", (alias[0],)).fetchone()
                return self._to_type(row) if row else None
        return None

    def official_exact(self, query: str, *, include_unmarketable: bool = False) -> EveType | None:
        normalized = normalize_name(query)
        market_filter = "" if include_unmarketable else "AND t.market_group_id IS NOT NULL"
        with self._connect() as db:
            rows = db.execute(
                f"""SELECT DISTINCT t.* FROM types t
                   JOIN type_names n ON n.type_id = t.type_id
                   WHERE n.normalized_name = ? AND t.published = 1
                         {market_filter}
                   LIMIT 2""",
                (normalized,),
            ).fetchall()
        return self._to_type(rows[0]) if len(rows) == 1 else None

    def search(
        self,
        query: str,
        limit: int = 5,
        *,
        include_blueprints: bool = False,
        include_skins: bool = False,
    ) -> list[EveType]:
        normalized = normalize_name(query)
        if not normalized:
            return []
        escaped = normalized.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        market_filter = "" if include_blueprints else "AND t.market_group_id IS NOT NULL"
        with self._connect() as db:
            rows = db.execute(
                f"""SELECT DISTINCT t.*, n.normalized_name AS matched_name
                   FROM types t JOIN type_names n ON n.type_id = t.type_id
                   WHERE t.published = 1 {market_filter}
                     AND n.normalized_name LIKE ? ESCAPE '!'
                   ORDER BY CASE WHEN n.normalized_name LIKE ? ESCAPE '!' THEN 0 ELSE 1 END,
                            length(n.normalized_name), t.type_id
                   LIMIT 100""",
                (f"%{escaped}%", f"{escaped}%"),
            ).fetchall()
            if not rows:
                lower = max(1, len(normalized) - 5)
                upper = len(normalized) + 8
                rows = db.execute(
                    f"""SELECT t.*, n.normalized_name AS matched_name
                       FROM types t JOIN type_names n ON n.type_id = t.type_id
                       WHERE t.published = 1 {market_filter}
                         AND length(n.normalized_name) BETWEEN ? AND ?
                         AND substr(n.normalized_name, 1, 1) = substr(?, 1, 1)
                       LIMIT 1500""",
                    (lower, upper, normalized),
                ).fetchall()
        scored: dict[int, tuple[float, sqlite3.Row]] = {}
        for row in rows:
            matched = row["matched_name"]
            score = (
                1.0 if matched == normalized else SequenceMatcher(None, normalized, matched).ratio()
            )
            if normalized in matched:
                score += 0.35
            previous = scored.get(row["type_id"])
            if previous is None or score > previous[0]:
                scored[row["type_id"]] = (score, row)
        ordered = sorted(scored.values(), key=lambda pair: (-pair[0], pair[1]["type_id"]))
        result = []
        for score, row in ordered:
            if score < 0.45:
                continue
            item = self._to_type(row)
            is_blueprint = self._is_blueprint(item)
            is_skin = self._is_skin(item)
            if include_blueprints and not is_blueprint:
                continue
            if not include_blueprints and is_blueprint:
                continue
            if include_skins and not is_skin:
                continue
            if not include_skins and is_skin:
                continue
            result.append(item)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _is_blueprint(item: EveType) -> bool:
        return "蓝图" in (item.name_zh or "") or "blueprint" in item.name_en.casefold()

    @staticmethod
    def _is_skin(item: EveType) -> bool:
        return "涂装" in (item.name_zh or "") or "skin" in item.name_en.casefold()

    def add_alias(self, alias: str, type_id: int, created_by: str = "") -> None:
        item = self.get_type(type_id)
        if item is None or not item.published or item.market_group_id is None:
            raise ValueError(f"物品 ID {type_id} 不存在或不可交易")
        normalized = normalize_name(alias)
        if not normalized:
            raise ValueError("别名不能为空")
        with self._connect() as db:
            official = db.execute(
                "SELECT type_id FROM type_names WHERE normalized_name = ? LIMIT 1", (normalized,)
            ).fetchone()
            if official and int(official[0]) != type_id:
                raise ValueError("别名与其他物品的官方名称冲突")
            existing = db.execute(
                "SELECT type_id FROM aliases WHERE normalized_alias = ?", (normalized,)
            ).fetchone()
            if existing and int(existing[0]) != type_id:
                raise ValueError("该别名已指向其他物品")
            db.execute(
                """INSERT INTO aliases(normalized_alias, alias, type_id, created_by)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(normalized_alias) DO UPDATE SET
                     alias = excluded.alias, type_id = excluded.type_id,
                     created_by = excluded.created_by, created_at = CURRENT_TIMESTAMP""",
                (normalized, alias.strip(), type_id, created_by),
            )

    def remove_alias(self, alias: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM aliases WHERE normalized_alias = ?", (normalize_name(alias),)
            )
        return cursor.rowcount > 0

    def list_aliases(self) -> list[tuple[str, EveType]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT a.alias, t.* FROM aliases a
                   JOIN types t ON t.type_id = a.type_id ORDER BY a.alias"""
            ).fetchall()
        return [(row["alias"], self._to_type(row)) for row in rows]

    @staticmethod
    def _to_type(row: sqlite3.Row) -> EveType:
        return EveType(
            type_id=int(row["type_id"]),
            name_en=row["name_en"],
            name_zh=row["name_zh"],
            group_id=row["group_id"],
            market_group_id=row["market_group_id"],
            published=bool(row["published"]),
        )
