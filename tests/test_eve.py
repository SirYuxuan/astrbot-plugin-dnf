import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

from plugin.features.eve.catalog import EveCatalog, EveType, normalize_name
from plugin.features.eve.client import (
    EsiMarketClient,
    MarketQuote,
    MemoryOrderCache,
    RedisOrderCache,
    _CacheEntry,
)
from plugin.features.eve.sde import SdeUpdater
from plugin.features.eve.service import EveFeature


class EveCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog = EveCatalog(Path(self.temp.name) / "eve.db")
        self.items = [
            EveType(34, "Tritanium", "三钛合金", 18, 1857, True),
            EveType(17918, "Rattlesnake", "响尾蛇级", 27, 161, True),
            EveType(17715, "Gila", "毒蜥级", 26, 161, True),
            EveType(17716, "Gila Blueprint", "毒蜥级蓝图", 9, None, True),
            EveType(17717, "Gila Blue SKIN", "毒蜥级蓝色涂装", 1950, 1950, True),
            EveType(17718, "Gila PA", "毒蜥级 PA", 26, 161, True),
            EveType(44992, "PLEX", "伊甸币", 1875, 1923, True),
            EveType(999, "Hidden Item", "隐藏物品", 1, None, True),
        ]
        self.catalog.replace_types(self.items, 123)

    def test_chinese_english_and_fuzzy_search(self):
        self.assertEqual(self.catalog.exact("三钛合金").type_id, 34)
        self.assertEqual(self.catalog.exact("TRITANIUM").type_id, 34)
        self.assertEqual(self.catalog.search("响尾蛇")[0].type_id, 17918)
        self.assertEqual(self.catalog.search("Rattlesnak")[0].type_id, 17918)
        default_gila = self.catalog.search("毒蜥级", limit=5)
        self.assertEqual([item.type_id for item in default_gila], [17715, 17718])
        blueprints = self.catalog.search("毒蜥级蓝图", include_blueprints=True)
        self.assertEqual([item.type_id for item in blueprints], [17716])
        skins = self.catalog.search("毒蜥级涂装", include_skins=True)
        self.assertEqual([item.type_id for item in skins], [17717])
        self.assertEqual(self.catalog.search("%"), [])
        self.assertEqual(normalize_name("  ＰＬＥＸ  "), "plex")

    def test_alias_validation_and_persistence_across_sde_update(self):
        self.catalog.add_alias("三钛", 34, "admin")
        self.assertEqual(self.catalog.exact("三钛").type_id, 34)
        self.assertEqual(self.catalog.list_aliases()[0][1].display_name, "三钛合金 Tritanium")
        with self.assertRaises(ValueError):
            self.catalog.add_alias("PLEX", 34)
        with self.assertRaises(ValueError):
            self.catalog.add_alias("隐藏", 999)
        self.catalog.replace_types(self.items, 124)
        self.assertEqual(self.catalog.exact("三钛").type_id, 34)


class EveServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        catalog = EveCatalog(Path(self.temp.name) / "eve.db")
        catalog.replace_types(
            [
                EveType(17715, "Gila", "毒蜥级", 26, 161, True),
                EveType(17716, "Gila Blueprint", "毒蜥级蓝图", 9, None, True),
                EveType(17717, "Gila Blue SKIN", "毒蜥级蓝色涂装", 1950, 1950, True),
                EveType(17718, "Gila PA", "毒蜥级 PA", 26, 161, True),
                EveType(17918, "Rattlesnake", "响尾蛇级", 27, 161, True),
                EveType(44992, "PLEX", "伊甸币", 1875, 1923, True),
            ],
            123,
        )
        self.catalog = catalog
        self.market = Mock()
        self.market.quote.side_effect = lambda type_id, market: MarketQuote(
            type_id, "Global PLEX Market" if market == "global" else "吉他 4-4", 10.0, 9.0
        )
        self.updater = Mock()
        self.feature = EveFeature(catalog, self.market, self.updater)

    async def test_unified_command_chinese_english_and_plex(self):
        chinese = await self.feature.handle("/jt 17715")
        english = await self.feature.handle("/jita 17918")
        plex = await self.feature.handle("/jt PLEX")
        chinese_plex = await self.feature.handle("/jita 伊甸币")
        self.assertIn("中间价：9.50 ISK", chinese)
        self.assertIn("中间价：9.50 ISK", english)
        self.assertNotIn("吉他 4-4", chinese)
        self.assertNotIn("数据来源", chinese)
        self.assertNotIn("Global PLEX Market", plex)
        self.assertNotIn("Global PLEX Market", chinese_plex)
        self.assertEqual(
            self.market.quote.call_args_list,
            [
                unittest.mock.call(17715, "jita"),
                unittest.mock.call(17918, "jita"),
                unittest.mock.call(44992, "global"),
                unittest.mock.call(44992, "global"),
            ],
        )

    async def test_plex_id_uses_global_market_and_quantity_is_rejected(self):
        self.assertNotIn("Global PLEX Market", await self.feature.handle("/jt 44992"))
        self.market.quote.assert_called_once_with(44992, "global")
        self.assertIn("只查询物品单价", await self.feature.handle("/jt PLEX * 500"))

    async def test_admin_alias_commands_use_target_name(self):
        denied = await self.feature.handle("/jt 别名 添加 毒蛇 Rattlesnake")
        self.assertIn("管理员", denied)
        added = await self.feature.handle(
            "/jt 别名 添加 毒蛇 Rattlesnake", is_admin=True, actor="42"
        )
        self.assertIn("已添加", added)
        self.assertIn("响尾蛇级", await self.feature.handle("/jt 毒蛇"))

    async def test_related_results_exclude_blueprints_and_skins_by_default(self):
        text = await self.feature.handle("/jt 毒蜥级")
        self.assertIn("毒蜥级 Gila", text)
        self.assertIn("毒蜥级 PA", text)
        self.assertNotIn("蓝图", text)
        self.assertNotIn("涂装", text)
        self.market.quote.assert_not_called()

    async def test_explicit_blueprint_and_skin_queries_are_allowed(self):
        blueprint = await self.feature.handle("/jt 毒蜥级蓝图")
        skin = await self.feature.handle("/jt Gila Blue SKIN")
        self.assertIn("毒蜥级蓝图", blueprint)
        self.assertIn("毒蜥级蓝色涂装", skin)
        self.assertEqual(self.market.quote.call_count, 2)

    async def test_candidate_limit_is_configurable(self):
        feature = EveFeature(self.catalog, self.market, self.updater, search_result_limit=1)
        text = await feature.handle("/jt 毒蜥级")
        self.assertIn("请使用 /jt <ID>", text)
        self.assertNotIn("毒蜥级 PA", text)
        self.market.quote.assert_not_called()

    async def test_ambiguous_name_returns_candidates_without_market_request(self):
        text = await self.feature.handle("/jt 响尾蛇")
        self.assertIn("请使用 /jt <ID>", text)
        self.market.quote.assert_not_called()

    def test_middle_price_requires_both_sides(self):
        item = EveType(17715, "Gila", "毒蜥级")
        text = self.feature._format_quote(item, MarketQuote(17715, "吉他 4-4", 10.0, None))
        self.assertIn("最低卖价：10.00 ISK", text)
        self.assertIn("最高收价：暂无报价", text)
        self.assertIn("中间价：暂无报价", text)


class SdeTests(unittest.TestCase):
    def test_reads_current_jsonl_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "sde.zip"
            record = {
                "_key": 34,
                "name": {"en": "Tritanium", "zh": "三钛合金"},
                "groupID": 18,
                "marketGroupID": 1857,
                "published": True,
            }
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("archetypes.jsonl", json.dumps({"_key": "wrong"}) + "\n")
                bundle.writestr("types.jsonl", json.dumps(record) + "\n")
            items = SdeUpdater._read_types(archive)
            self.assertEqual(items, [EveType(34, "Tritanium", "三钛合金", 18, 1857, True)])


class MarketClientTests(unittest.TestCase):
    def test_memory_cache_preserves_pagination_metadata(self):
        cache = MemoryOrderCache()
        entry = _CacheEntry([], 9999999999, '"etag"', "today", 3)
        cache.set("key", entry)
        self.assertIs(cache.get("key"), entry)
        self.assertEqual(cache.get("key").pages, 3)

    def test_redis_failure_falls_back_to_memory(self):
        cache = RedisOrderCache("redis://localhost:6379/15", prefix="test:eve")
        cache._redis = Mock()
        cache._redis.setex.side_effect = OSError("redis down")
        cache._redis.get.side_effect = OSError("redis down")
        entry = _CacheEntry([], 9999999999, None, "today", 2)
        with self.assertLogs("plugin.features.eve.client", level="WARNING"):
            cache.set("key", entry)
            loaded = cache.get("key")
        self.assertIs(loaded, entry)

    def test_jita_filters_station_and_aggregates_orders(self):
        client = EsiMarketClient(cache=MemoryOrderCache())
        client._get_page = Mock(
            return_value=(
                [
                    {
                        "location_id": 60003760,
                        "is_buy_order": False,
                        "price": 11,
                        "volume_remain": 3,
                    },
                    {
                        "location_id": 60003760,
                        "is_buy_order": False,
                        "price": 10,
                        "volume_remain": 4,
                    },
                    {"location_id": 60003760, "is_buy_order": True, "price": 9, "volume_remain": 5},
                    {"location_id": 1, "is_buy_order": False, "price": 1, "volume_remain": 99},
                ],
                1,
                "today",
            )
        )
        quote = client.quote(34)
        self.assertEqual((quote.sell_min, quote.buy_max), (10, 9))
