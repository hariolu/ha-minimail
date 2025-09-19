# custom_components/minimail/sensor_usps.py
from __future__ import annotations
from typing import Any, Dict
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from calendar import month_name

from .const import ENTITY_PREFIX

_MONTH_INDEX = {name: i for i, name in enumerate(month_name) if name}

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
    def _root(self) -> Dict[str, Any]:
        return self.coordinator.data or {}
    def _usps(self) -> Dict[str, Any]:
        return (self._root().get("usps") or {})
    def _usps_delivered(self) -> Dict[str, Any]:
        # <-- patched to read under usps['last_delivered']
        u = self._usps() or {}
        return (u.get("last_delivered") or {})

class UspsSubject(_Base):
    """Readable subject of the latest USPS email (Digest or Delivered)."""
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Subject", "usps_subject")
    @property
    def state(self) -> str:
        return str((self._usps().get("subject") or "")).strip()
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        u = self._usps()
        ld = self._usps_delivered()
        return {
            "type": u.get("type", ""),                # "digest" / "delivered"
            "last_delivered_subject": ld.get("subject", ""),
            "dashboard_url": u.get("dashboard_url", ""),
        }

class UspsSubjectDigest(_Base):
    """Subject of the latest USPS Daily Digest (explicit)."""
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Subject (Digest)", "usps_subject_digest")
    @property
    def state(self) -> str:
        return str((self._usps().get("subject_digest") or "")).strip()
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        dig = (self._usps().get("digest") or {})
        return {
            "date_iso": str(dig.get("date_iso", "")),
            "date_label": str(dig.get("date_label", "")),
            "dashboard_url": str(self._usps().get("dashboard_url", "")),
        }

class UspsSubjectDelivered(_Base):
    """Subject of the latest USPS Delivered (explicit)."""
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Subject (Delivered)", "usps_subject_delivered")
    @property
    def state(self) -> str:
        # Prefer nested last_delivered.subject; fallback to flat field if set
        ld = self._usps_delivered()
        return str(ld.get("subject") or self._usps().get("subject_delivered") or "").strip()
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        ld = self._usps_delivered()
        y = int(ld.get("year", 0) or 0)
        m = _MONTH_INDEX.get(str(ld.get("month", "")).strip(), 0)
        d = int(ld.get("day", 0) or 0)
        iso = f"{y:04d}-{m:02d}-{d:02d}" if (y and m and d) else ""
        return {
            "date_iso": iso,
            "date_label": str(ld.get("date_label", "")),
            "dashboard_url": str(ld.get("dashboard_url", "")),
        }
class UspsMailpiecesExpectedToday(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Mailpieces Expected Today", "usps_mailpieces_expected_today")
    @property
    def state(self) -> int:
        v = self._usps().get("mail_expected", None)
        return int(v) if v is not None else 0

class UspsPackagesExpectedToday(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Packages Expected Today", "usps_packages_expected_today")
    @property
    def state(self) -> int:
        v = self._usps().get("pkgs_expected", None)
        return int(v) if v is not None else 0

class UspsMailFrom(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Mail From", "usps_mail_from")
    @property
    def state(self) -> str:
        lst = list(self._usps().get("mail_from", []) or [])
        return ", ".join(lst[:3]) if lst else ""
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {"from": list(self._usps().get("mail_from", []) or []), "dashboard_url": self._usps().get("dashboard_url", "")}

class UspsPackagesFrom(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Packages From", "usps_packages_from")
    @property
    def state(self) -> str:
        lst = list(self._usps().get("pkgs_from", []) or [])
        return ", ".join(lst[:3]) if lst else ""
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {"from": list(self._usps().get("pkgs_from", []) or []), "dashboard_url": self._usps().get("dashboard_url", "")}

class UspsStatusDigest(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Status Digest", "usps_status_digest")
    @property
    def state(self) -> str:
        u = self._usps(); b = u.get("buckets") or {}
        et = int((b.get("expected_today") or {}).get("count", 0) or 0)
        afs = int((b.get("awaiting_from_sender") or {}).get("count", 0) or 0)
        return f"Today:{et} | Awaiting:{afs}"
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        u = self._usps()
        return {"buckets": u.get("buckets", {}), "dashboard_url": u.get("dashboard_url", "")}

class UspsTrackingUrl(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Tracking URL", "usps_tracking_url")
    @property
    def state(self) -> str:
        return ""
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {"tracking_urls": list(self._usps().get("tracking_urls", []) or []), "dashboard_url": self._usps().get("dashboard_url", "")}

class UspsScans(_Base):
    def __init__(self, c, d, ns): super().__init__(c, d, ns, "USPS Scans", "usps_scans")
    @property
    def state(self) -> int:
        mi = (self._usps().get("mail_images") or {}) if isinstance(self._usps().get("mail_images"), dict) else {}
        try: return int(mi.get("count", 0) or 0)
        except Exception: return 0
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        usps = self._usps(); mi = usps.get("mail_images", {}) or {}
        urls = list(mi.get("urls", []) or []); files = list(mi.get("files", []) or [])
        images = list(usps.get("images", []) or urls)
        return {"urls": urls, "files": files, "images": images, "first_url": urls[0] if urls else "", "dashboard_url": usps.get("dashboard_url", "")}

class UspsLastDelivered(_Base):
    def __init__(self, c, d, ns):
        super().__init__(c, d, ns, "USPS Last Delivered", "usps_last_delivered")

    @property
    def state(self) -> str:
        u = self._usps_delivered()
        y = int(u.get("year", 0) or 0)
        m = _MONTH_INDEX.get(str(u.get("month", "")).strip(), 0)
        d = int(u.get("day", 0) or 0)
        return f"{y:04d}-{m:02d}-{d:02d}" if (y and m and d) else str(u.get("date_label", ""))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        u = self._usps_delivered()
        y = int(u.get("year", 0) or 0)
        m = _MONTH_INDEX.get(str(u.get("month", "")).strip(), 0)
        d = int(u.get("day", 0) or 0)
        iso = f"{y:04d}-{m:02d}-{d:02d}" if (y and m and d) else ""
        return {
            "delivered": bool(u.get("delivered", False)),
            "date_label": str(u.get("date_label", "")),
            "month": str(u.get("month", "")),
            "day": d,
            "year": y,
            "subject": str(u.get("subject", "")),
            "dashboard_url": str(u.get("dashboard_url", "")),
            "iso_date": iso,
        }

# exported factory list
USPS_ENTITIES = [
    UspsSubject,
    UspsSubjectDigest,
    UspsSubjectDelivered,
    UspsMailpiecesExpectedToday,
    UspsPackagesExpectedToday,
    UspsMailFrom,
    UspsPackagesFrom,
    UspsStatusDigest,
    UspsTrackingUrl,
    UspsScans,
    UspsLastDelivered,
]
