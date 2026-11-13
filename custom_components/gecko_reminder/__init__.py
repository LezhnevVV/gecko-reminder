"""Gecko Reminder integration."""

from pathlib import Path

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
    store = Store(hass, 1, DOMAIN)
    saved = await store.async_load()
    journal = FeedingJournal(saved["entries"] if saved else [], store.async_save)
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

    hass.services.async_register(DOMAIN, "save_feeding", handle_upsert, schema=FEEDING_SCHEMA)
    hass.services.async_register(DOMAIN, "delete_feeding", handle_delete,
                                 schema=vol.Schema({vol.Required("id"): cv.string}))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.services.async_remove(DOMAIN, "save_feeding")
    hass.services.async_remove(DOMAIN, "delete_feeding")
    hass.data.pop(DOMAIN)
    return True
