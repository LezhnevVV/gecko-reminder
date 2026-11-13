"""UI setup for a single-pet journal."""

import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN


class GeckoReminderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            name = user_input["name"].strip()
            if name:
                return self.async_create_entry(title=name, data={"name": name})
            return self.async_show_form(step_id="user", data_schema=self._schema(),
                                        errors={"name": "empty_name"})
        return self.async_show_form(step_id="user", data_schema=self._schema())

    @staticmethod
    def _schema():
        return vol.Schema({vol.Required("name", default="Эублефар"): vol.All(str, vol.Length(max=80))})
