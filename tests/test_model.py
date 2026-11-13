"""Run with python3 -m unittest discover -s tests -v; no HA install required."""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest

# Load the pure model without executing the HA integration's __init__.
ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "gecko_reminder"
PACKAGE = "gecko_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(f"{PACKAGE}.model", ROOT / "model.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

FEEDING = {"date": "2026-11-11", "insect": "cricket", "count": 5, "supplement": "calcium"}


class JournalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = None

        async def save(data):
            await asyncio.sleep(0)
            self.saved = data

        self.journal = model.FeedingJournal([], save)

    async def test_create_edit_delete_and_reload(self):
        await self.journal.upsert(FEEDING)
        entry_id = self.journal.entries[0]["id"]
        await self.journal.upsert({**FEEDING, "count": 3}, entry_id)
        self.assertEqual(len(self.journal.entries), 1)
        self.assertEqual(self.journal.entries[0]["count"], 3)
        reloaded = model.FeedingJournal(self.saved["entries"], self.journal._save)
        self.assertEqual(reloaded.entries, self.journal.entries)
        await self.journal.delete(entry_id)
        self.assertEqual(self.saved, {"entries": []})

    async def test_concurrent_adds_and_multiple_feedings_per_day(self):
        await asyncio.gather(*(self.journal.upsert(FEEDING) for _ in range(20)))
        self.assertEqual(len(self.saved["entries"]), 20)
        self.assertEqual(len({e["id"] for e in self.journal.entries}), 20)

    async def test_storage_failure_keeps_previous_state(self):
        await self.journal.upsert(FEEDING)
        old_entries = list(self.journal.entries)

        async def fail(data):
            raise OSError("disk unavailable")

        self.journal._save = fail
        with self.assertRaises(OSError):
            await self.journal.upsert({**FEEDING, "count": 2}, old_entries[0]["id"])
        self.assertEqual(self.journal.entries, old_entries)
        with self.assertRaises(OSError):
            await self.journal.delete(old_entries[0]["id"])
        self.assertEqual(self.journal.entries, old_entries)

    async def test_missing_entry_is_not_recreated(self):
        with self.assertRaises(ValueError):
            await self.journal.upsert(FEEDING, "missing")
        with self.assertRaises(ValueError):
            await self.journal.delete("missing")
        self.assertIsNone(self.saved)

    async def test_count_boundaries_on_create_and_edit(self):
        await self.journal.upsert({**FEEDING, "count": 1})
        entry_id = self.journal.entries[0]["id"]
        await self.journal.upsert({**FEEDING, "count": 99}, entry_id)
        self.assertEqual(self.journal.entries[0]["count"], 99)
        with self.assertRaises(ValueError):
            await self.journal.upsert({**FEEDING, "count": 100}, entry_id)
        self.assertEqual(self.journal.entries[0]["count"], 99)
        self.assertEqual(self.saved["entries"][0]["count"], 99)

    async def test_interval_persistence_and_recalculation(self):
        self.assertIsNone(self.journal.next_feeding)
        await self.journal.set_interval(3)
        self.assertIsNone(self.journal.next_feeding)
        await self.journal.upsert({**FEEDING, "date": "2024-02-27"})
        self.assertEqual(self.journal.next_feeding, "2024-03-01")
        entry_id = self.journal.entries[0]["id"]
        restored = model.FeedingJournal(self.saved["entries"], self.journal._save,
                                        self.saved["feeding_interval_days"])
        self.assertEqual(restored.next_feeding, "2024-03-01")
        await self.journal.upsert({**FEEDING, "date": "2024-12-31"}, entry_id)
        self.assertEqual(self.journal.next_feeding, "2025-01-03")
        await self.journal.delete(entry_id)
        self.assertIsNone(self.journal.next_feeding)
        self.assertEqual(self.saved["feeding_interval_days"], 3)
        await self.journal.set_interval(None)
        self.assertNotIn("feeding_interval_days", self.saved)

    async def test_interval_validation_failure_and_concurrency(self):
        for days in (0, -1, 366, 1.5, True, "3"):
            with self.subTest(days=days), self.assertRaises(ValueError):
                await self.journal.set_interval(days)
        await asyncio.gather(self.journal.set_interval(365), self.journal.upsert(FEEDING))
        self.assertEqual(self.saved["feeding_interval_days"], 365)
        self.assertEqual(len(self.saved["entries"]), 1)

        async def fail(data):
            raise OSError("disk unavailable")

        self.journal._save = fail
        with self.assertRaises(OSError):
            await self.journal.set_interval(1)
        self.assertEqual(self.journal.feeding_interval_days, 365)

    async def test_validation(self):
        for patch in ({"date": "2026-02-30"}, {"date": "20261111"}, {"date": None},
                      {"count": 0}, {"count": 1.5}, {"count": True}, {"count": 100}, {"count": 1000},
                      {"count": "3"}, {"insect": "unknown"}, {"supplement": "unknown"},
                      {"notes": "x" * 501}, {"notes": None}, {"extra": "field"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                await self.journal.upsert({**FEEDING, **patch})
        self.assertEqual(self.journal.entries, [])

    async def test_leap_day_and_chronological_order(self):
        await self.journal.upsert(FEEDING)
        await self.journal.upsert({**FEEDING, "date": "2024-02-29", "notes": "  Заметка  "})
        self.assertEqual(self.journal.entries[0]["date"], "2024-02-29")
        self.assertEqual(self.journal.entries[0]["notes"], "Заметка")


if __name__ == "__main__":
    unittest.main()
