from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any, Dict
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

class MailCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client, update_interval: int):
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name="minimail",
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        return await self.client.fetch()
