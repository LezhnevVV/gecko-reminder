"""Reminder policy with a fake sender; no Telegram messages are sent."""

import asyncio
from datetime import datetime, timezone, timedelta
import unittest

from test_model import model, FEEDING


class ReminderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = None
        self.sent = []

        async def save(data):
            self.saved = data

        self.journal = model.FeedingJournal([], save)
        await self.journal.upsert(FEEDING)
        await self.journal.set_settings(3, {"enabled": True, "time": "19:00", "target": "notify.telegram_pet"})

    async def send(self, target, due):
        self.sent.append((target, due))

    def time(self, day=14, hour=19, minute=0):
        return datetime(2026, 11, day, hour, minute, tzinfo=timezone(timedelta(hours=5)))

    async def test_due_time_and_once_per_day_across_restart(self):
        self.assertFalse(await self.journal.send_reminder_if_due(self.time(13), self.send))
        self.assertFalse(await self.journal.send_reminder_if_due(self.time(hour=18, minute=59), self.send))
        await asyncio.gather(*(self.journal.send_reminder_if_due(self.time(), self.send) for _ in range(2)))
        self.assertEqual(self.sent, [("notify.telegram_pet", "2026-11-14")])
        restored = model.FeedingJournal(self.saved["entries"], self.journal._save,
            self.saved["feeding_interval_days"], self.saved["reminder"], self.saved["last_reminder_date"])
        self.assertFalse(await restored.send_reminder_if_due(self.time(hour=20), self.send))
        self.assertTrue(await restored.send_reminder_if_due(self.time(15), self.send))

    async def test_recording_feeding_stops_reminder_and_future_entries_do_not(self):
        await self.journal.upsert({**FEEDING, "date": "2026-12-01"})
        self.assertTrue(await self.journal.send_reminder_if_due(self.time(), self.send))
        await self.journal.upsert({**FEEDING, "date": "2026-11-15"})
        self.assertFalse(await self.journal.send_reminder_if_due(self.time(15), self.send))

    async def test_no_history_disabled_and_catchup(self):
        await self.journal.set_settings(3, {**self.journal.reminder, "enabled": False})
        self.assertFalse(await self.journal.send_reminder_if_due(self.time(), self.send))
        await self.journal.set_settings(3, {**self.journal.reminder, "enabled": True})
        self.assertTrue(await self.journal.send_reminder_if_due(self.time(hour=22), self.send))
        await self.journal.delete(self.journal.entries[0]["id"])
        self.assertFalse(await self.journal.send_reminder_if_due(self.time(15), self.send))

    async def test_send_failure_retries_without_recording_success(self):
        async def fail(target, due):
            raise RuntimeError("provider unavailable")
        with self.assertRaises(RuntimeError):
            await self.journal.send_reminder_if_due(self.time(), fail)
        self.assertIsNone(self.journal.last_reminder_date)
        self.assertTrue(await self.journal.send_reminder_if_due(self.time(minute=1), self.send))

    async def test_invalid_settings_and_storage_failure_are_atomic(self):
        original = dict(self.journal.reminder)
        for patch in ({"time": "24:00"}, {"time": "9:00"}, {"target": "telegram.send"},
                      {"target": "notify.send_message"}, {"target": ""}, {"enabled": "true"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                await self.journal.set_settings(3, {**original, **patch})
        with self.assertRaises(ValueError):
            await self.journal.set_settings(None, original)
        async def fail(data):
            raise OSError("disk unavailable")
        self.journal._save = fail
        with self.assertRaises(OSError):
            await self.journal.set_settings(5, {**original, "time": "20:00"})
        self.assertEqual(self.journal.reminder, original)
        self.assertEqual(self.journal.feeding_interval_days, 3)

    async def test_old_journal_starts_with_reminders_disabled(self):
        old = model.FeedingJournal(self.journal.entries, self.journal._save, 3)
        self.assertFalse(await old.send_reminder_if_due(self.time(), self.send))
