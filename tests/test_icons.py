"""Tests for icons.json — icon translations for entities without a device class."""

from homeassistant.helpers.icon import async_get_icons


async def test_entities_without_device_class_have_an_icon(
    hass, init_integration, entity_registry
):
    icons = (await async_get_icons(hass, "entity", ["xenia_home"]))["xenia_home"]
    missing = [
        entry.entity_id
        for entry in entity_registry.entities.values()
        if entry.platform == "xenia_home"
        and entry.domain != "event"
        and entry.original_device_class is None
        and entry.translation_key not in icons.get(entry.domain, {})
    ]
    assert missing == []


async def test_status_sensor_has_state_icons(hass, init_integration):
    icons = (await async_get_icons(hass, "entity", ["xenia_home"]))["xenia_home"]
    assert set(icons["sensor"]["status"]["state"]) <= {
        "off",
        "on",
        "eco",
        "brewing",
        "draining",
    }
