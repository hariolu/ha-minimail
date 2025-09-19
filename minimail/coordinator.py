from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any, Dict
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

class MailCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client, update_interval: int):
        self.client = client
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._live_once = False

        super().__init__(
            hass,
            _LOGGER,
            name="minimail",
            update_interval=timedelta(seconds=update_interval),
        )

    async def async_restore(self) -> None:
        """Load last snapshot from disk and expose it immediately with status=restoring."""
        snap = await self._store.async_load()
        data: Dict[str, Any] = {}
        if isinstance(snap, dict):
            # warm the client and coordinator
            try:
                if hasattr(self.client, "seed"):
                    self.client.seed(snap)
            except Exception:  # best-effort
                pass
            data = dict(snap)
        else:
            data = {"usps": {}, "amazon": {}}
        data["_status"] = "restoring"
        self.async_set_updated_data(data)

    async def _async_update_data(self) -> Dict[str, Any]:
        # fetch fresh data
        data = await self.client.fetch()
        # persist snapshot without transient keys
        try:
            await self._store.async_save({
                "usps": data.get("usps", {}),
                "amazon": data.get("amazon", {}),
            })
        except Exception:
            _LOGGER.debug("MiniMail: failed to save snapshot", exc_info=True)
        # mark 'live' after the first successful fetch
        out = dict(data)
        out["_status"] = "live"
        self._live_once = True
        return out
