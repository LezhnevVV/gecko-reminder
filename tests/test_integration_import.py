"""Check integration import with real Voluptuous and minimal HA substitutes.

This catches invalid validation API calls at import time, without installing HA.
It does not test the actual Home Assistant config-flow lifecycle.
"""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import voluptuous as vol


class IntegrationImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = {}
        exports = {
            "homeassistant": {},
            "homeassistant.components": {},
            "homeassistant.components.http": {"StaticPathConfig": object},
            "homeassistant.config_entries": {"ConfigEntry": object},
            "homeassistant.core": {"HomeAssistant": object, "ServiceCall": object},
            "homeassistant.exceptions": {"ServiceValidationError": ValueError},
            "homeassistant.helpers": {},
            "homeassistant.helpers.config_validation": {
                "string": str,
                "config_entry_only_config_schema": lambda domain: None,
            },
            "homeassistant.helpers.dispatcher": {"async_dispatcher_send": lambda *args: None},
            "homeassistant.helpers.storage": {"Store": object},
        }
        for name, attributes in exports.items():
            module = types.ModuleType(name)
            module.__dict__.update(attributes)
            modules[name] = module
        for name, module in modules.items():
            parent, _, child = name.rpartition(".")
            if parent in modules:
                setattr(modules[parent], child, module)

        source = Path(__file__).resolve().parents[1] / "custom_components/gecko_reminder/__init__.py"
        spec = importlib.util.spec_from_file_location("gecko_import_test", source)
        integration = importlib.util.module_from_spec(spec)
        modules[spec.name] = integration
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(integration)
        cls.schema = integration.FEEDING_SCHEMA

    def test_integration_import_and_valid_service_data(self):
        for count in (1, 5, 99):
            with self.subTest(count=count):
                feeding = {"date": "2026-11-13", "insect": "cricket", "count": count, "supplement": "calcium"}
                self.assertEqual(self.schema(feeding), {**feeding, "notes": ""})

    def test_service_schema_rejects_invalid_count(self):
        for count in (0, 100, 1000, 1.5, "5", None):
            with self.subTest(count=count), self.assertRaises(vol.Invalid):
                self.schema({"date": "2026-11-13", "insect": "cricket",
                             "count": count, "supplement": "none"})
