import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from plugin.core.config import DEFAULT_CONFIG, PluginConfig
from plugin.core.runtime import FeatureRuntime
from plugin.core.storage import JsonFileStore


class ConfigTests(unittest.TestCase):
    def test_partial_override_and_unknown_sections(self):
        config = PluginConfig({"gold": {"interval_seconds": 90}, "retired": {"key": "secret"}})
        self.assertEqual(config.get("gold.interval_seconds"), 90)
        self.assertTrue(config.get("gold.monitor_enabled"))
        self.assertIsNone(config.get("retired"))

    def test_input_does_not_share_mutable_values(self):
        raw = {"oil": {"monitor_areas": ["北京"]}}
        config = PluginConfig(raw)
        raw["oil"]["monitor_areas"].append("上海")
        self.assertEqual(config.get("oil.monitor_areas"), ["北京"])
        self.assertEqual(PluginConfig().get("oil.monitor_areas"), ["河南"])

    def test_supported_wrappers_and_invalid_section(self):
        for raw in (
            SimpleNamespace(data={"gold": {"monitor_enabled": False}}),
            SimpleNamespace(to_dict=lambda: {"gold": {"monitor_enabled": False}}),
        ):
            self.assertFalse(PluginConfig(raw).get("gold.monitor_enabled"))
        self.assertEqual(PluginConfig({"oil": None}).get("oil.check_hour"), 8)

    def test_schema_matches_defaults_exactly(self):
        schema = json.loads((Path(__file__).parents[1] / "_conf_schema.json").read_text())
        defaults = {
            name: {key: item["default"] for key, item in section["items"].items()}
            for name, section in schema.items()
        }
        self.assertEqual(defaults, DEFAULT_CONFIG)
        self.assertEqual(
            set(defaults),
            {
                "platform",
                "gold",
                "oil",
                "egg",
                "rat",
                "info",
                "translate",
                "ship",
                "ship_training",
                "eve_dt",
                "kb",
                "kb_watch",
                "eve",
            },
        )


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = JsonFileStore(Path(self.temp.name) / "new")

    def test_roundtrip(self):
        self.store.save("state.json", {"地区": "河南"})
        self.assertEqual(self.store.load("state.json", {}), {"地区": "河南"})

    def test_corrupt_and_missing_return_independent_default(self):
        self.store.path("state.json").write_text("{broken")
        default = {"values": []}
        with self.assertLogs("plugin.core.storage", level="WARNING"):
            result = self.store.load("state.json", default)
        result["values"].append(1)
        self.assertEqual(default, {"values": []})
        self.assertEqual(self.store.load("missing.json", []), [])

    def test_atomic_write_failure_keeps_old_file(self):
        self.store.save("state.json", {"value": 1})
        with patch("plugin.core.storage.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                self.store.save("state.json", {"value": 2})
        self.assertEqual(self.store.load("state.json", {}), {"value": 1})
        self.assertEqual(list(self.store.base_dir.iterdir()), [self.store.path("state.json")])

    def test_legacy_migration_is_non_destructive_and_new_state_wins(self):
        legacy = Path(self.temp.name) / "old"
        legacy.mkdir()
        old = legacy / "state.json"
        old.write_text('{"value": 1}')
        store = JsonFileStore(self.store.base_dir, legacy)
        self.assertEqual(store.load("state.json", {}), {"value": 1})
        self.assertTrue(old.exists())
        store.save("state.json", {"value": 2})
        self.assertEqual(store.load("state.json", {}), {"value": 2})

    def test_path_traversal_rejected(self):
        for filename in ("../state.json", "/tmp/state.json", "", ".", ".."):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                self.store.load(filename, {})


class FakeFeature:
    def __init__(self, name="test", enabled=True):
        self.name = name
        self.enabled = enabled
        self.started = 0
        self.stopped = 0

    async def run(self):
        self.started += 1
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped += 1


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_stop_are_idempotent_and_can_restart(self):
        feature = FakeFeature()
        runtime = FeatureRuntime((feature,))
        await asyncio.gather(runtime.start(), runtime.start())
        await asyncio.sleep(0)
        self.assertEqual(feature.started, 1)
        await asyncio.gather(runtime.stop(), runtime.stop())
        self.assertEqual(feature.stopped, 1)
        await runtime.start()
        await asyncio.sleep(0)
        await runtime.stop()
        self.assertEqual((feature.started, feature.stopped), (2, 2))

    async def test_disabled_feature_not_started(self):
        feature = FakeFeature(enabled=False)
        runtime = FeatureRuntime((feature,))
        await runtime.start()
        await asyncio.sleep(0)
        await runtime.stop()
        self.assertEqual(feature.started, 0)

    async def test_crashed_feature_does_not_prevent_stopping_others(self):
        class Broken(FakeFeature):
            async def run(self):
                raise RuntimeError("boom")

        healthy = FakeFeature()
        runtime = FeatureRuntime((healthy, Broken(name="broken")))
        with self.assertLogs("plugin.core.runtime", level="ERROR"):
            await runtime.start()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await runtime.stop()
        self.assertEqual(healthy.stopped, 1)

    async def test_duplicate_names_rejected(self):
        with self.assertRaises(ValueError):
            FeatureRuntime((FakeFeature(), FakeFeature()))
