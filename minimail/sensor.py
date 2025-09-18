# custom_components/minimail/sensor.py
from __future__ import annotations
from typing import List, Dict, Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    DOMAIN, DEVICE_NAME, ENTITY_PREFIX,
    CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD, CONF_FOLDER, CONF_SSL,
    CONF_SENDER_FILTERS, CONF_SEARCH, CONF_FETCH_LIMIT, CONF_UPDATE_INTERVAL,
    DEFAULT_PORT, DEFAULT_SSL, DEFAULT_FOLDER, DEFAULT_FETCH_LIMIT, DEFAULT_UPDATE_INTERVAL, DEFAULT_SEARCH,
)
from .sensor_usps import USPS_ENTITIES
from .sensor_amazon import AMAZON_ENTITIES
from .imap_client import ImapClient
from .coordinator import MailCoordinator

# ---- Platform schema (валидирует keys из sensors.yaml) ----
PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
        vol.Optional(CONF_FOLDER, default=DEFAULT_FOLDER): cv.string,
        vol.Optional(CONF_SEARCH, default=DEFAULT_SEARCH): cv.string,
        vol.Optional(CONF_SENDER_FILTERS, default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_FETCH_LIMIT, default=DEFAULT_FETCH_LIMIT): vol.Coerce(int),
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.Coerce(int),
    }
)

async def _ensure_coordinator_from_platform(hass: HomeAssistant, config: Dict[str, Any]):
    """Create coordinator when integration is configured as a sensor platform."""
    store = hass.data.setdefault(DOMAIN, {})
    coordinator = store.get("coordinator")
    if coordinator is not None:
        return coordinator, store.get("namespace", ENTITY_PREFIX) or ENTITY_PREFIX

    client = ImapClient(hass, config)
    coordinator = MailCoordinator(hass, client, update_interval=config[CONF_UPDATE_INTERVAL])
    # первичный refresh чтобы появились данные
    await coordinator.async_config_entry_first_refresh()

    store["coordinator"] = coordinator
    store["namespace"] = ENTITY_PREFIX
    return coordinator, store["namespace"]

async def _instantiate_all(hass: HomeAssistant) -> List[SensorEntity]:
    store = hass.data.get(DOMAIN, {})
    coordinator = store.get("coordinator")
    if coordinator is None:
        return []
    ns = store.get("namespace", ENTITY_PREFIX) or ENTITY_PREFIX
    device_info = DeviceInfo(
        identifiers={(DOMAIN, ns)},
        name=DEVICE_NAME,
        model="MiniMail",
        manufacturer="CVBot",
    )
    return [factory(coordinator, device_info, ns) for factory in (USPS_ENTITIES + AMAZON_ENTITIES)]

# sensors.yaml (`- platform: minimail`)
async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    await _ensure_coordinator_from_platform(hass, config)   # <-- создаём координатор
    entities = await _instantiate_all(hass)
    if entities:
        add_entities(entities, True)

# config_entry path (на будущее; не мешает)
async def async_setup_entry(hass: HomeAssistant, _entry: ConfigEntry, async_add_entities) -> None:
    entities = await _instantiate_all(hass)
    if entities:
        async_add_entities(entities, True)
