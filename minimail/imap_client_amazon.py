# custom_components/minimail/imap_client_amazon.py
from __future__ import annotations

from typing import Any, Dict, Tuple
from email.message import Message

# Try rules/amazon.py first (new layout), then amazon.py (root).
# If neither exists, define a safe no-op stub so the integration can start.
try:
    from .rules.amazon import parse_amazon_email  # type: ignore
except Exception:  # pragma: no cover
    try:
        from .amazon import parse_amazon_email  # type: ignore
    except Exception:  # pragma: no cover
        def parse_amazon_email(_msg: Message) -> Dict[str, Any]:
            """Fallback stub: no Amazon parser installed yet."""
            return {}

def handle_amazon(msg: Message, amazon: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Merge parsed Amazon fields into the coordinator's amazon dict.
    Returns (amazon_dict, got_any_data).
    """
    a = parse_amazon_email(msg) or {}

    # Only overwrite when parser actually returned something non-empty.
    updated = False
    for k in (
        "subject", "event", "items", "track_url",
        "order_id", "shipment_id", "package_index", "eta"
    ):
        v = a.get(k)
        if v not in (None, "", []):
            amazon[k] = v
            updated = True

    return amazon, updated
