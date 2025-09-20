# custom_components/minimail/imap_client_amazon.py
from __future__ import annotations

from typing import Any, Dict, Tuple
from email.message import Message
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from datetime import timezone

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

def _msg_timestamp(msg: Message) -> float:
    """Epoch seconds from Date header (UTC). 0.0 on failure."""
    try:
        dt = parsedate_to_datetime(msg.get('Date'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0

def _safe_subject(msg: Message) -> str:
    try:
        return str(make_header(decode_header(msg.get('Subject', '') or ''))).strip()
    except Exception:
        return msg.get('Subject', '') or ''

def handle_amazon(msg: Message, amazon: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Parse a single Amazon email and merge into the running 'amazon' dict.

    IMPORTANT: We only overwrite existing values if this message is NEWER than what
    we already have (tracked via amazon['ts']). This prevents older messages
    processed later from clobbering the latest state.
    """
    amazon = dict(amazon or {})
    new_ts = _msg_timestamp(msg)
    old_ts = float(amazon.get('ts') or 0.0)

    a = parse_amazon_email(msg) or {}
    if not a:
        return amazon, False

    # Ignore if message is older than what we have
    if new_ts < old_ts:
        return amazon, False

    updated = False
    for k in ('subject', 'event', 'items', 'track_url',
              'order_id', 'shipment_id', 'package_index', 'eta'):
        v = a.get(k)
        if v not in (None, '', []):
            if amazon.get(k) != v:
                amazon[k] = v
                updated = True

    # Stamp freshest timestamp (even if content identical)
    if new_ts and new_ts != old_ts:
        amazon['ts'] = new_ts
        updated = True or updated

    # Ensure subject is not empty
    if not amazon.get('subject'):
        amazon['subject'] = _safe_subject(msg)

    return amazon, updated
