"""Gecko Reminder integration."""

from pathlib import Path
import asyncio
import logging

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN, INSECTS, SUPPLEMENTS, UPDATE_SIGNAL
from .model import FeedingJournal

PLATFORMS = ["sensor"]
LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
FEEDING_SCHEMA = vol.Schema({
    vol.Optional("id"): cv.string,
    vol.Required("date"): cv.string,
    vol.Required("insect"): vol.In(INSECTS),
    vol.Required("count"): vol.All(int, vol.Range(min=1, max=99)),
    vol.Required("supplement"): vol.In(SUPPLEMENTS),
    vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the bundled card; HA retains this route across entry reloads."""
    await hass.http.async_register_static_paths([
        StaticPathConfig("/gecko_reminder/gecko-feeding-card.js",
                         str(Path(__file__).parent / "frontend" / "gecko-feeding-card.js"),
                         cache_headers=False)
    ])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.helpers.event import async_track_time_change
    from homeassistant.util import dt as dt_util

    store = Store(hass, 1, DOMAIN)
    saved = await store.async_load()
    journal = FeedingJournal(saved["entries"] if saved else [], store.async_save,
                             saved.get("feeding_interval_days") if saved else None,
                             saved.get("reminder") if saved else None,
                             saved.get("last_reminder_date") if saved else None)
    hass.data[DOMAIN] = journal
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_upsert(call: ServiceCall):
        data = dict(call.data)
        entry_id = data.pop("id", None)
        try:
            await journal.upsert(data, entry_id)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        async_dispatcher_send(hass, UPDATE_SIGNAL)

    async def handle_delete(call: ServiceCall):
        try:
            await journal.delete(call.data["id"])
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        async_dispatcher_send(hass, UPDATE_SIGNAL)

    async def handle_settings(call: ServiceCall):
        try:
            await journal.set_interval(call.data["feeding_interval_days"])
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        async_dispatcher_send(hass, UPDATE_SIGNAL)

    async def handle_save_settings(call: ServiceCall):
        data = call.data
        target = data["reminder_target"].strip()
        if data["reminder_enabled"] and not (
            (hass.states.get(target) is not None and hass.services.has_service("notify", "send_message"))
            or hass.services.has_service("notify", target.removeprefix("notify."))
        ):
            raise ServiceValidationError("Получатель не найден. Сначала настройте Telegram Bot в Home Assistant")
        try:
            await journal.set_settings(data["feeding_interval_days"], {
                "enabled": data["reminder_enabled"], "time": data["reminder_time"], "target": target,
            })
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        async_dispatcher_send(hass, UPDATE_SIGNAL)

    async def send_notification(target, due):
        message = ("🦎 Пора покормить питомца! Дата кормления: "
                   + ".".join(reversed(due.split("-")))
                   + ". После кормления отметьте его в календаре Home Assistant.")
        if hass.states.get(target) is not None:
            await hass.services.async_call("notify", "send_message",
                                           {"entity_id": target, "message": message}, blocking=True)
        else:
            await hass.services.async_call("notify", target.removeprefix("notify."),
                                           {"message": message}, blocking=True)

    active = True
    running_checks = set()

    async def check_reminder(_now):
        if not active:
            return
        task = asyncio.current_task()
        running_checks.add(task)
        try:
            if await journal.send_reminder_if_due(dt_util.now(), send_notification):
                async_dispatcher_send(hass, UPDATE_SIGNAL)
        except Exception as err:
            # Provider exceptions may contain credentials or private recipient data.
            LOGGER.warning("Feeding reminder failed (%s); check notification integration", type(err).__name__)
        finally:
            running_checks.discard(task)

    def stop_reminders():
        nonlocal active
        active = False
        for task in tuple(running_checks):
            task.cancel()

    hass.services.async_register(DOMAIN, "save_settings", handle_save_settings, schema=vol.Schema({
        vol.Required("feeding_interval_days"): vol.Any(None, vol.All(int, vol.Range(min=1, max=365))),
        vol.Required("reminder_enabled"): bool,
        vol.Required("reminder_time"): cv.string,
        vol.Required("reminder_target"): cv.string,
    }))

    hass.services.async_register(DOMAIN, "set_feeding_interval", handle_settings,
                                 schema=vol.Schema({vol.Required("feeding_interval_days"):
                                                    vol.Any(None, vol.All(int, vol.Range(min=1, max=365)))}))
    hass.services.async_register(DOMAIN, "save_feeding", handle_upsert, schema=FEEDING_SCHEMA)
    hass.services.async_register(DOMAIN, "delete_feeding", handle_delete,
                                 schema=vol.Schema({vol.Required("id"): cv.string}))
    entry.async_on_unload(async_track_time_change(hass, check_reminder, second=0))
    entry.async_on_unload(stop_reminders)
    startup_check = hass.async_create_task(check_reminder(None))
    entry.async_on_unload(startup_check.cancel)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.services.async_remove(DOMAIN, "save_feeding")
    hass.services.async_remove(DOMAIN, "delete_feeding")
    hass.services.async_remove(DOMAIN, "set_feeding_interval")
    hass.services.async_remove(DOMAIN, "save_settings")
    hass.data.pop(DOMAIN)
    return True
