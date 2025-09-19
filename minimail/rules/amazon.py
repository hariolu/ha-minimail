# custom_components/minimail/rules/amazon.py
# Always code in English; comments in English.

from __future__ import annotations

import re
import email
from typing import Dict, List, Tuple
from email.message import Message
from urllib.parse import urlparse, parse_qs


def _extract_parts(msg: Message) -> Tuple[str, str]:
    """Return (html, text) bodies concatenated from all MIME parts."""
    html, text = [], []
    for part in msg.walk():
        ctype = (part.get_content_type() or "").lower()
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            s = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        except Exception:
            s = ""
        if ctype == "text/html":
            html.append(s)
        elif ctype == "text/plain":
            text.append(s)
    return " ".join(html), "\n".join(text)


# Progress-tracker link
_RE_TRACK = re.compile(
    r'https?://www\.amazon\.com/progress-tracker/package[^ \n<>"\']+',
    re.I,
)

# ETA like "Arriving September 9", "Delivery estimate Sep 9", "Arrives Today/Tomorrow"
_RE_ETA = re.compile(
    r'(?:(Arriving|Delivery estimate|Estimated delivery|Arrives)\s*:?\s*)'
    r'(Today|Tomorrow|[A-Z][a-z]{2,9}\s+\d{1,2}(?:,\s*\d{4})?)',
    re.I,
)

# Item lines in plaintext: "* Item name"
_RE_ITEM_LI = re.compile(r'^\s*\*\s+(.+)$', re.M)

# Item titles in HTML near dp/gp/product links
_RE_ITEM_HTML = re.compile(
    r'(?:<li[^>]*>\s*)?(?:<a[^>]+href="https?://www\.amazon\.com/(?:dp|gp/product)/[^"]+"[^>]*>)'
    r'([^<]{2,300})</a>',
    re.I,
)

# Visible headline in HTML cards (e.g., "Your package was delivered!", "Out for delivery")
_RE_HTML_HEADLINE = re.compile(
    r'(Your package was delivered!|Out for delivery|Your order has shipped|Shipped|'
    r'Order confirmed|Order placed|Ordered|We\'ve received your order)',  # Ordered variants
    re.I,
)


def _items_from_text(text: str) -> List[str]:
    """Extract item titles from plaintext bullets."""
    items = []
    for m in _RE_ITEM_LI.finditer(text or ""):
        name = m.group(1).strip()
        # Trim quantity tails when present
        name = re.split(r'\s{2,}Quantity:|  Quantity:', name)[0].strip()
        items.append(name)
    return items


def _items_from_html(html: str) -> List[str]:
    """Extract item titles from HTML links; fallback to generic <li> contents."""
    items = [m.group(1).strip() for m in _RE_ITEM_HTML.finditer(html or "")]
    if not items:
        for m in re.finditer(r'<li[^>]*>\s*([^<]{2,200})\s*</li>', html or "", re.I):
            items.append(m.group(1).strip())
    # Normalize spacing / nbsp and dedupe preserving order
    items = [re.sub(r'\s+', ' ', x.replace('\xa0', ' ')).strip() for x in items]
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _event_from_subject_or_html(subject: str, html: str) -> str:
    """Infer a compact event label: ordered | shipped | out_for_delivery | delivered | ''."""
    subj = (subject or "").lower()

    # Ordered/Order-confirmation subjects
    if (
        subj.startswith("ordered:")
        or " order confirmed" in subj
        or "order confirmation" in subj
        or "we've received your order" in subj
        or "your order has been placed" in subj
        or "order placed" in subj
    ):
        return "ordered"

    if subj.startswith("shipped:") or " has shipped" in subj or "your order has shipped" in subj:
        return "shipped"

    if "out for delivery" in subj:
        return "out_for_delivery"

    if subj.startswith("delivered:") or " delivered" in subj:
        return "delivered"

    # Fallback: detect from an HTML headline on the card
    m = _RE_HTML_HEADLINE.search(html or "")
    if m:
        t = m.group(1).lower()
        if "ordered" in t or "order confirmed" in t or "order placed" in t:
            return "ordered"
        if "shipped" in t or "has shipped" in t:
            return "shipped"
        if "out for delivery" in t:
            return "out_for_delivery"
        if "delivered" in t:
            return "delivered"

    return ""


def _parse_track_params(url: str) -> Dict[str, str]:
    """Extract orderId/shipmentId/packageIndex from the tracker URL."""
    try:
        q = parse_qs(urlparse(url).query)
        return {
            "order_id": (q.get("orderId") or [""])[0],
            "shipment_id": (q.get("shipmentId") or [""])[0],
            "package_index": (q.get("packageIndex") or [""])[0],
        }
    except Exception:
        return {"order_id": "", "shipment_id": "", "package_index": ""}


def parse_amazon_email(msg: Message) -> Dict:
    """
    Single-argument signature to match imap_client_amazon.handle_amazon().
    Subject is safely decoded from the Message object.
    Returns dict with keys:
        subject, headline, event, items(list[str]),
        track_url, order_id, shipment_id, package_index, eta
    """
    html, text = _extract_parts(msg)

    # Decode subject defensively
    try:
        subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", "")))).strip()
    except Exception:
        subject = msg.get("Subject", "") or ""

    event = _event_from_subject_or_html(subject, html)

    # Items
    items = _items_from_text(text) or _items_from_html(html)

    # Tracker URL and IDs
    track_url = ""
    m = _RE_TRACK.search(text or "") or _RE_TRACK.search(html or "")
    if m:
        track_url = m.group(0)
    ids = _parse_track_params(track_url) if track_url else {"order_id": "", "shipment_id": "", "package_index": ""}

    # ETA (best-effort)
    eta = ""
    m_eta = _RE_ETA.search(text or "") or _RE_ETA.search(html or "")
    if m_eta:
        eta = f"{m_eta.group(1).strip()} {m_eta.group(2).strip()}"

    # Human headline from HTML (optional)
    headline = ""
    m_head = _RE_HTML_HEADLINE.search(html or "")
    if m_head:
        headline = m_head.group(1).strip()

    return {
        "subject": subject or headline or "",
        "headline": headline,
        "event": event,
        "items": items,
        "track_url": track_url,
        "order_id": ids.get("order_id", ""),
        "shipment_id": ids.get("shipment_id", ""),
        "package_index": ids.get("package_index", ""),
        "eta": eta,
    }
