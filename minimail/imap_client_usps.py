# custom_components/minimail/imap_client_usps.py
# USPS-specific handlers (called from the main ImapClient loop)

from __future__ import annotations
from typing import Any, Dict, Tuple
from email.message import Message
from email.header import decode_header, make_header

# Robust imports for USPS parsers
try:
    from .rules.usps_digest import parse_usps_digest  # type: ignore
except Exception:  # pragma: no cover
    try:
        from .usps_digest import parse_usps_digest  # type: ignore
    except Exception:  # pragma: no cover
        from .rules.usps import parse_usps_digest  # type: ignore

try:
    from .rules.usps_delivered import parse_usps_delivered  # type: ignore
except Exception:  # pragma: no cover
    from .usps_delivered import parse_usps_delivered  # type: ignore

_DASH = "https://informeddelivery.usps.com/portal/dashboard"


def _decode_subject(msg: Message) -> str:
    try:
        return str(make_header(decode_header(msg.get("Subject", "") or "")))
    except Exception:
        return msg.get("Subject", "") or ""


def handle_usps_delivered(msg: Message, usps: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Update usps['last_delivered'] from a 'Your Mail Was Delivered …' email."""
    d = parse_usps_delivered(msg) or {}
    dash = d.get("dashboard_url") or usps.get("dashboard_url") or _DASH

    # Keep a readable subject for UI/bot; mark type
    usps["subject"] = _decode_subject(msg)
    usps["type"] = "delivered"

    # IMPORTANT: also expose dashboard on the root for other sensors
    usps["dashboard_url"] = dash

    # Do NOT touch digest fields; only set the nested delivered payload
    usps["last_delivered"] = {
        "subject": d.get("subject", ""),
        "delivered": bool(d.get("delivered", True)),
        "date_label": d.get("date_label", ""),
        "month": d.get("month", ""),
        "day": int(d.get("day", 0) or 0),
        "year": int(d.get("year", 0) or 0),
        "dashboard_url": dash,
    }
    return usps, True


def handle_usps_digest(msg: Message, usps: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Merge counters, names, buckets and images from a USPS digest email."""
    p = parse_usps_digest(msg) or {}

    # Save current readable subject and type for UI/bot
    usps["subject"] = _decode_subject(msg)
    usps["type"] = "digest"

    # Core counters & lists
    usps["mail_expected"] = p.get("mail_expected", usps.get("mail_expected"))
    usps["pkgs_expected"] = p.get("pkgs_expected", usps.get("pkgs_expected"))
    usps["mail_from"] = list(p.get("mail_from", usps.get("mail_from", [])) or [])
    usps["pkgs_from"] = list(p.get("pkgs_from", usps.get("pkgs_from", [])) or [])
    usps["dashboard_url"] = p.get("dashboard_url", usps.get("dashboard_url", "")) or usps.get("dashboard_url", "")

    # Buckets
    buckets = p.get("buckets") or {}
    for k in ("expected_today", "expected_1_2_days", "awaiting_from_sender", "outbound"):
        if isinstance(buckets.get(k), dict):
            cur = usps.setdefault("buckets", {}).get(k, {"count": 0, "from": []})
            try:
                cur["count"] = int(buckets[k].get("count", cur.get("count", 0)) or 0)
            except Exception:
                cur["count"] = cur.get("count", 0) or 0
            cur["from"] = list(buckets[k].get("from", cur.get("from", [])) or [])
            usps["buckets"][k] = cur

    # Mailpiece images
    mi = p.get("mail_images") or p.get("mailpiece_images") or {}
    if isinstance(mi, dict):
        safe = {
            "count": int(mi.get("count", 0) or 0),
            "urls": list(mi.get("urls", []) or []),
            "files": list(mi.get("files", []) or []),
        }
        usps["mail_images"] = safe
        usps["images"] = list(safe["urls"])
    else:
        usps.setdefault("mail_images", {"count": 0, "urls": [], "files": []})
        usps.setdefault("images", [])

    return usps, True
