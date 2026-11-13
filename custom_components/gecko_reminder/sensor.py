"""Expose journal data to the dashboard without duplicating it in Recorder."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, UPDATE_SIGNAL


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FeedingSensor(hass.data[DOMAIN], entry)])


class FeedingSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Feedings"
    _attr_icon = "mdi:calendar-check"
    _attr_should_poll = False
    _unrecorded_attributes = frozenset({"entries"})

    def __init__(self, journal, entry):
        self._journal = journal
        self._attr_unique_id = f"{entry.entry_id}_feedings"
        self._attr_suggested_object_id = "gecko_reminder_feedings"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name=entry.title,
            manufacturer="Gecko Reminder", model="Feeding journal")

    @property
    def native_value(self):
        return len(self._journal.entries)

    @property
    def extra_state_attributes(self):
        entries = self._journal.entries
        return {"entries": entries, "last_feeding": entries[-1]["date"] if entries else None}

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(
            self.hass, UPDATE_SIGNAL, self.async_write_ha_state))
