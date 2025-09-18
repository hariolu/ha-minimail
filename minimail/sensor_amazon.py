from __future__ import annotations
from typing import Any, Dict, List
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

# Keep Amazon sensors consistent with USPS ones
# coordinator.data structure is provided by MailCoordinator/ImapClient
# Expected keys under root["amazon"]:
#   subject, event, items(list[str]), track_url, order_id, shipment_id, package_index, eta

class _Base(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, device_info: DeviceInfo, namespace: str, friendly: str, key: str) -> None:
        super().__init__(coordinator)
        self._attr_name = f"Minimail {friendly}"
        self._attr_unique_id = f"{namespace}_{key}"
        self._namespace = namespace
        self._device_info = device_info

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

    # Root dict from coordinator
    def _root(self) -> Dict[str, Any]:
        return self.coordinator.data or {}

    # Amazon subtree
    def _amazon(self) -> Dict[str, Any]:
        return (self._root().get("amazon") or {})

class AmazonSubject(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "Amazon Subject", "amazon_subject")
    @property
    def state(self) -> str:
        return str(self._amazon().get("subject", "") or "")
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {"track_url": str(self._amazon().get("track_url", "") or "")}

class AmazonLastEvent(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "Amazon Last Event", "amazon_last_event")
    @property
    def state(self) -> str:
        return str(self._amazon().get("event", "") or "")
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {"eta": str(self._amazon().get("eta", "") or ""), "track_url": str(self._amazon().get("track_url", "") or "")}

class AmazonItems(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "Amazon Items", "amazon_items")
    @property
    def state(self) -> str:
        # A short, human-readable summary (first 3 items)
        items: List[str] = list(self._amazon().get("items", []) or [])
        return ", ".join(items[:3]) if items else ""
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        items: List[str] = list(self._amazon().get("items", []) or [])
        return {"items": items, "count": len(items)}

class AmazonTrackUrl(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "Amazon Track URL", "amazon_track_url")
    @property
    def state(self) -> str:
        return str(self._amazon().get("track_url", "") or "")

class AmazonOrderId(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "Amazon Order ID", "amazon_order_id")
    @property
    def state(self) -> str:
        return str(self._amazon().get("order_id", "") or "")

class AmazonShipmentId(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "Amazon Shipment ID", "amazon_shipment_id")
    @property
    def state(self) -> str:
        return str(self._amazon().get("shipment_id", "") or "")

class AmazonPackageIndex(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "Amazon Package Index", "amazon_package_index")
    @property
    def state(self) -> str:
        return str(self._amazon().get("package_index", "") or "")

class AmazonEta(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "Amazon ETA", "amazon_eta")
    @property
    def state(self) -> str:
        return str(self._amazon().get("eta", "") or "")

# exported factory list (must match what's imported in sensor.py)
AMAZON_ENTITIES = [
    lambda c,d,ns: AmazonSubject(c,d,ns),
    lambda c,d,ns: AmazonLastEvent(c,d,ns),
    lambda c,d,ns: AmazonItems(c,d,ns),
    lambda c,d,ns: AmazonTrackUrl(c,d,ns),
    lambda c,d,ns: AmazonOrderId(c,d,ns),
    lambda c,d,ns: AmazonShipmentId(c,d,ns),
    lambda c,d,ns: AmazonPackageIndex(c,d,ns),
    lambda c,d,ns: AmazonEta(c,d,ns),
]
