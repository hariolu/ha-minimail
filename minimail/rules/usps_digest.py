# custom_components/minimail/rules/usps.py
# ---------------------------------------------------------------
# USPS Informed Delivery parser for MiniMail.
# - Robustly extracts counts and sender names from multiple templates.
# - Preserves mailpiece count parity (keeps duplicate "Envelope" entries).
# - Uses strict "FROM:" detection (requires a colon) to avoid "From Sender" noise.
# - Does NOT blacklist "USPSIS" (so "FROM: USPSIS" is shown when present).
# - Enriches "Awaiting From Sender" names from pkgs_from when count > listed names.
# - Optionally extracts inline CID images of mailpieces to /config/www/minimail/usps.
# ---------------------------------------------------------------
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple
from email.message import Message
from email.utils import parsedate_to_datetime
from datetime import datetime

# Stable USPS dashboard link (also returned via sensor attribute)
_DASHBOARD_URL = "https://informeddelivery.usps.com/portal/dashboard"

# ---------------------------------------------------------------------------
# MIME helpers
# ---------------------------------------------------------------------------

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


def _strip_tags(s: str) -> str:
    """Flatten HTML to whitespace-normalized text."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _dedup_keep_order(items: List[str]) -> List[str]:
    """De-duplicate while preserving original order."""
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _smart_case(s: str) -> str:
    """If ALL CAPS, convert to Title Case; otherwise keep original."""
    if not s:
        return s
    has_upper = any(ch.isupper() for ch in s)
    has_lower = any(ch.islower() for ch in s)
    if has_upper and not has_lower:
        return s.title()
    return s


def _clean_label(name: str) -> str:
    """
    Normalize sender labels:
      - drop 'FROM:' prefix (tolerate ASCII/Unicode colons)
      - strip promo tails like 'Learn more about your mail'
      - strip tracking-like numbers and quantifiers '... 2 item(s)'
      - drop trailing 'FROM'
      - trim punctuation and squeeze spaces
    """
    n = name or ""
    n = re.sub(r"^\s*FROM\s*[:：]\s*", "", n, flags=re.I)
    n = re.sub(r"\bLearn more about your mail\b", "", n, flags=re.I)
    n = re.sub(r"\bOutbound\b.*$", "", n, flags=re.I)
    n = re.sub(r"\b\d+\s+item[s]?\b.*$", "", n, flags=re.I)
    n = re.sub(r"\d{6,}", "", n)  # tracking-like digit blobs
    n = re.sub(r"\bFROM\b$", "", n, flags=re.I)
    n = re.sub(r"[•–—\-:;,]+$", "", n).strip()
    n = re.sub(r"\s{2,}", " ", n).strip(" ,")
    return _smart_case(n)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Bucket section titles
_SEC = {
    "expected_today": r"Expected\s+Today",
    "expected_1_2_days": r"Expected\s+1[\-–—]\s*2\s+Days",
    "awaiting_from_sender": r"Awaiting\s+From\s+Sender",
    "outbound": r"Outbound",
}
_RE_SECERS = {k: re.compile(v, re.I) for k, v in _SEC.items()}

# Counts inside a section (e.g., "2 item(s)")
_RE_COUNT_ITEMS = re.compile(r"\b(\d+)\s*item(?:s)?\b", re.I)

# Fallback USPS tracking-like number (starts with 9..., 16+ digits)
_RE_TRACK = re.compile(r"\b9\d{15,}\b")

# STRICT "FROM:" (require colon to avoid matching "From Sender")
_FROM_COLON_RX = re.compile(r"\bFROM\s*[:：]\s*([A-Z0-9 .,&/&\-]{2,200})", re.I)

# Structured spans found in some templates
_RE_MAIL_FROM_SPAN = re.compile(r'id=["\']campaign-from-span-id["\'][^>]*>\s*([^<>\r\n]+)', re.I)
_RE_SHIPPER_SPAN   = re.compile(r'id=["\']pra-shipper-name-id["\'][^>]*>\s*([^<>\r\n]+)', re.I)

# Big counters (if present in HTML)
_RE_MAIL_BIG = re.compile(r'id="(?:bg-total-mailpieces|total-mailpieces[^"]*)"\s*>\s*(\d+)', re.I)
_RE_PKG_BIG  = re.compile(r'id="(?:bg-total-packages|total-packages[^"]*)"\s*>\s*(\d+)', re.I)

# Inline CID images (mail scans)
_RE_CAMPAIGN_IMG_CID = re.compile(
    r'id=["\']campaign-representative-image-src-id["\'][^>]+src=["\']cid:([^"\']+)',
    re.I,
)
_RE_MAILPIECE_IMG_CID = re.compile(
    r'id=["\']mailpiece-div-id["\'][\s\S]*?src=["\']cid:([^"\']+)',
    re.I,
)

# ---------------------------------------------------------------------------
# Text splitting / section extraction
# ---------------------------------------------------------------------------

def _split_sections(flat: str) -> Dict[str, str]:
    """Split flattened text by known section headers."""
    hits = []
    for key, rx in _RE_SECERS.items():
        for m in rx.finditer(flat):
            hits.append((m.start(), key))
    hits.sort()
    out: Dict[str, str] = {k: "" for k in _SEC.keys()}
    for i, (pos, key) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(flat)
        out[key] = flat[pos:end]
    return out

# ---------------------------------------------------------------------------
# Counting + names per section
# ---------------------------------------------------------------------------

def _bucket_count_and_names(seg: str) -> Tuple[int, List[str]]:
    """
    Compute count and sample sender names for a section.

    Priority:
      1) explicit textual counter “N item(s)”
      2) explicit FROM: lines → names (and count by len(names))  [require colon]
      3) fallback: count tracking-like numbers
    """
    seg = seg or ""

    # 1) Prefer explicit counter if present
    m = _RE_COUNT_ITEMS.search(seg)
    explicit_count = int(m.group(1)) if m else None

    # 2) Gather names (only strict FROM:)
    names = [_clean_label(m2.group(1)) for m2 in _FROM_COLON_RX.finditer(seg)]
    names = [x for x in names if x]

    if explicit_count is not None:
        # Keep the explicit count and return up to a few example names
        tops = _dedup_keep_order(names)[:5]
        return explicit_count, tops

    if names:
        uniq = _dedup_keep_order(names)
        return len(uniq), uniq[:5]

    # 3) Fallback — count tracking IDs
    tracks = _RE_TRACK.findall(seg)
    return len(tracks), []

# ---------------------------------------------------------------------------
# "Mail From" and "Packages From" extractors
# ---------------------------------------------------------------------------

def _mail_from(html: str, flat: str, pkg_sections: Dict[str, str]) -> List[str]:
    """
    Letter senders ("Mail From"):
      1) prefer structured span in campaign blocks
      2) fallback: strict FROM:… seen globally minus anything inside *package* sections
      3) DO NOT blacklist USPSIS (we want it if that's the sender)
    """
    out = [_clean_label(m.group(1)) for m in _RE_MAIL_FROM_SPAN.finditer(html)]
    out = [x for x in out if x]

    if not out:
        pkg_text = " ".join(pkg_sections.values())
        pkg_froms = {_clean_label(m.group(1)) for m in _FROM_COLON_RX.finditer(pkg_text)}
        all_from = []
        for m in _FROM_COLON_RX.finditer(flat):
            nm = _clean_label(m.group(1))
            if nm and nm not in pkg_froms:
                all_from.append(nm)
        out = all_from

    # Keep USPSIS; remove only generic USPS brand phrases
    blacklist = {
        "USPS", "USPS Informed Delivery", "United States Postal Service",
        "Informed Delivery", "U.S. Postal Service"
        # NOTE: 'USPSIS' deliberately NOT blacklisted
    }
    bl = {b.upper() for b in blacklist}
    clean = [x for x in out if x.upper() not in bl]

    # DO NOT de-duplicate here — we must preserve count parity with mail_expected.
    return [*clean][:10]


def _packages_from(html: str, sections: Dict[str, str]) -> List[str]:
    """Sender list for packages."""
    names = [_clean_label(m.group(1)) for m in _RE_SHIPPER_SPAN.finditer(html)]
    names = [x for x in names if x]
    if not names:
        for key in ("expected_today", "expected_1_2_days", "awaiting_from_sender", "outbound"):
            seg = sections.get(key, "") or ""
            for m in _FROM_COLON_RX.finditer(seg):
                nm = _clean_label(m.group(1))
                if nm:
                    names.append(nm)
    return _dedup_keep_order(names)[:10]

# ---------------------------------------------------------------------------
# Mailpiece CID images
# ---------------------------------------------------------------------------

def _email_dt(msg: Message) -> datetime:
    try:
        return parsedate_to_datetime(msg.get("Date"))
    except Exception:
        return datetime.utcnow()

def _safe_name(s: str, default: str = "mailpiece") -> str:
    s = (s or default).strip()
    s = re.sub(r"[^\w\-+.]+", "_", s, flags=re.U)
    return s[:64] or default

def _guess_ext(ctype: str, filename: str | None) -> str:
    if filename and "." in filename:
        return "." + filename.split(".")[-1].lower()
    if ctype.lower().endswith(("jpeg", "jpg")):
        return ".jpg"
    if ctype.lower().endswith("png"):
        return ".png"
    return ".bin"

def _save_mail_images(msg: Message, html: str, mail_from: List[str]) -> Dict[str, List[str] | int]:
    """Extract inline 'cid:' images of mailpieces to /config/www/minimail/usps."""
    cids = set(_RE_CAMPAIGN_IMG_CID.findall(html)) | set(_RE_MAILPIECE_IMG_CID.findall(html))
    if not cids:
        return {"files": [], "urls": [], "count": 0}

    # Build map CID -> part
    cid_map: Dict[str, Tuple[bytes, str, str | None]] = {}
    for part in msg.walk():
        if (part.get_content_maintype() or "").lower() != "image":
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        cid_header = (part.get("Content-ID") or "").strip()
        cid = cid_header.strip("<>") if cid_header else ""
        if not cid or cid not in cids:
            continue
        cid_map[cid] = (payload, (part.get_content_type() or "image/jpeg"), part.get_filename())

    if not cid_map:
        return {"files": [], "urls": [], "count": 0}

    base_dir = os.environ.get("HASS_CONFIG", "/config")
    out_dir = Path(base_dir) / "www" / "minimail" / "usps"
    out_dir.mkdir(parents=True, exist_ok=True)

    dt = _email_dt(msg)
    date_tag = dt.strftime("%Y%m%d_%H%M%S")

    files: List[str] = []
    urls: List[str] = []
    ordered = list(cids)
    for idx, cid in enumerate(ordered, start=1):
        blob, ctype, fname = cid_map.get(cid, (b"", "image/jpeg", None))
        if not blob:
            continue
        ext = _guess_ext(ctype, fname)
        sender_hint = _safe_name(mail_from[idx - 1] if idx - 1 < len(mail_from) else "mail")
        out_name = f"usps_{date_tag}_{idx:02d}_{sender_hint}{ext}"
        out_path = out_dir / out_name
        try:
            out_path.write_bytes(blob)
        except Exception:
            continue
        files.append(str(out_path))
        urls.append(f"/local/minimail/usps/{out_name}")

    return {"files": files, "urls": urls, "count": len(files)}

# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_usps_digest(msg: Message) -> Dict[str, object]:
    """
    Parse USPS Informed Delivery "Daily Digest".
    Returns dict with:
      mail_expected, pkgs_expected, mail_from (NOT deduped), pkgs_from,
      tracking_urls (empty), dashboard_url, buckets{...}, mail_images{...}
    """
    html, text = _extract_parts(msg)
    flat = _strip_tags(html)

    # Header counters (if present)
    m_mail = _RE_MAIL_BIG.search(html or "")
    m_pkg  = _RE_PKG_BIG.search(html or "")
    mail_expected = int(m_mail.group(1)) if m_mail else None
    pkgs_expected = int(m_pkg.group(1)) if m_pkg else None

    # Extra fallbacks for mail/packages counts (rare templates / forwarded text)
    if mail_expected is None:
        # Try "Mail Expected Today ... N" / "Mailpieces Expected Today: N"
        m = re.search(r'\bMail(?:pieces)?\s+Expected\s+Today\b[^0-9]{0,20}(\d+)', flat, re.I) or \
            re.search(r'\bMail(?:pieces)?\s+Expected\s+Today\b[^0-9]{0,20}(\d+)', text or "", re.I)
        if m:
            mail_expected = int(m.group(1))

    if pkgs_expected is None:
        m = re.search(r'\bPackages?\s+Expected\s+Today\b[^0-9]{0,20}(\d+)', flat, re.I) or \
            re.search(r'\bPackages?\s+Expected\s+Today\b[^0-9]{0,20}(\d+)', text or "", re.I)
        if m:
            pkgs_expected = int(m.group(1))

    # Sections → buckets
    sections = _split_sections(flat)
    buckets: Dict[str, Dict[str, object]] = {}
    for key in _SEC.keys():
        seg = sections.get(key, "") or ""
        c, tops = _bucket_count_and_names(seg)
        buckets[key] = {"count": int(c), "from": list(tops)}

    # From-lists
    pkg_sections = {k: sections.get(k, "") or "" for k in _SEC.keys()}
    mail_from = _mail_from(html, flat, pkg_sections)         # DO NOT dedup (we may need duplicates)
    pkgs_from = _packages_from(html, sections)               # OK to dedup

    # If "Awaiting From Sender" has a count but fewer (or zero) names, enrich from pkgs_from
    aw = buckets.get("awaiting_from_sender", {}) or {}
    aw_count = int(aw.get("count", 0) or 0)
    aw_names = list(aw.get("from", []) or [])
    if aw_count > len(aw_names):
        for nm in pkgs_from:
            if nm not in aw_names:
                aw_names.append(nm)
            if len(aw_names) >= min(aw_count, 5):
                break
        buckets["awaiting_from_sender"]["from"] = aw_names

    # Final fallbacks for counts if header spans are missing
    if mail_expected is None:
        mail_expected = len([x for x in mail_from if x])  # count known names; padded below if needed
    if pkgs_expected is None:
        pkgs_expected = sum((buckets.get(k, {}).get("count", 0) or 0)
                            for k in ("expected_today", "expected_1_2_days", "awaiting_from_sender", "outbound"))

    # If there are more mailpieces than explicit FROM names — pad with 'Envelope'
    if (mail_expected or 0) > len(mail_from):
        pads = (mail_expected or 0) - len(mail_from)
        mail_from = mail_from + (["Envelope"] * pads)

    # Mail scans (CID images) for future use
    mail_images = _save_mail_images(msg, html, mail_from)

    return {
        "mail_expected": int(mail_expected or 0),
        "pkgs_expected": int(pkgs_expected or 0),
        "mail_from": list(mail_from),                  # IMPORTANT: not deduped (parity with count)
        "pkgs_from": _dedup_keep_order(pkgs_from),
        "tracking_urls": [],                          # deep tracking links intentionally suppressed
        "dashboard_url": _DASHBOARD_URL,              # always set
        "buckets": buckets,
        "mail_images": mail_images,
        "mailpiece_images": mail_images,              # alias
    }
