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
        and entry.original_device_class is None
        and entry.translation_key not in icons.get(entry.domain, {})
    ]
    assert missing == []


async def test_state_icons_use_real_states(hass, init_integration):
    icons = (await async_get_icons(hass, "entity", ["xenia_home"]))["xenia_home"]
    status = hass.states.get("sensor.xenia_espresso_machine_status")
    assert set(icons["sensor"]["status"]["state"]) <= set(status.attributes["options"])
    assert set(icons["binary_sensor"]["water_tank_empty"]["state"]) <= {"on", "off"}
