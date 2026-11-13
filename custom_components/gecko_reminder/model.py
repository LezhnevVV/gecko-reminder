"""Persistent feeding journal, independent of Home Assistant."""

import asyncio
from datetime import date
from uuid import uuid4

from .const import INSECTS, SUPPLEMENTS


def validate_feeding(data):
    """Normalize user input without accepting unknown fields."""
    allowed = {"date", "insect", "count", "supplement", "notes"}
    if set(data) - allowed:
        raise ValueError("Неизвестные поля кормления")
    try:
        feeding_date = date.fromisoformat(data["date"])
    except (KeyError, TypeError, ValueError) as err:
        raise ValueError("Дата должна иметь формат YYYY-MM-DD") from err
    if feeding_date.isoformat() != data["date"]:
        raise ValueError("Дата должна иметь формат YYYY-MM-DD")
    if data.get("insect") not in INSECTS:
        raise ValueError("Выберите вид насекомого")
    if type(data.get("count")) is not int or not 1 <= data["count"] <= 99:
        raise ValueError("Количество должно быть целым числом от 1 до 99")
    if data.get("supplement") not in SUPPLEMENTS:
        raise ValueError("Выберите добавку")
    notes = data.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 500:
        raise ValueError("Заметка должна быть текстом не длиннее 500 символов")
    return {"date": feeding_date.isoformat(), "insect": data["insect"],
            "count": data["count"], "supplement": data["supplement"],
            "notes": notes.strip()}


class FeedingJournal:
    """Serialize mutations and expose changes only after successful persistence."""

    def __init__(self, entries, save):
        self.entries = entries
        self._save = save
        self._lock = asyncio.Lock()

    async def upsert(self, data, entry_id=None):
        feeding = validate_feeding(data)
        async with self._lock:
            if entry_id is not None and not any(e["id"] == entry_id for e in self.entries):
                raise ValueError("Запись не найдена. Обновите календарь")
            feeding["id"] = entry_id or uuid4().hex
            entries = [e for e in self.entries if e["id"] != feeding["id"]] + [feeding]
            entries.sort(key=lambda e: (e["date"], e["id"]))
            await self._save({"entries": entries})
            self.entries = entries

    async def delete(self, entry_id):
        async with self._lock:
            entries = [e for e in self.entries if e["id"] != entry_id]
            if len(entries) == len(self.entries):
                raise ValueError("Запись не найдена. Обновите календарь")
            await self._save({"entries": entries})
            self.entries = entries
