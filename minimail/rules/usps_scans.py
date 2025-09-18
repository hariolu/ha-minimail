# custom_components/minimail/rules/usps_scans.py
from __future__ import annotations

# NOTE: This module is pure-Python and safe to call from MiniMail's executor.
# It extracts inline CID images from a USPS digest email and saves them to
# /config/www/minimail/usps/YYYY-MM-DD/. It returns a list of public /local URLs.
#
# We keep it decoupled: no Home Assistant imports here.

import os
import re
import base64
from pathlib import Path
from email.message import Message
from datetime import datetime
from typing import List, Tuple

# Where to store images for HA to serve at /local/minimail/usps/...
ROOT = Path("/config/www/minimail/usps")

# Simple detect inline-image parts
_IMG_CTYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}

def _safe_name(s: str) -> str:
    # Make a filesystem-friendly name
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s)
    return s.strip("_") or "img"

def _pick_filename(part: Message, idx: int) -> str:
    # Prefer filename; fallback to CID; final fallback to index
    name = part.get_filename() or part.get("Content-ID") or f"image_{idx}.jpg"
    name = name.strip("<>")  # strip CID brackets
    name = _safe_name(name)
    # Force common extensions if missing
    if not re.search(r"\.(jpe?g|png|gif|webp)$", name, re.I):
        ctype = (part.get_content_type() or "").lower()
        ext = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }.get(ctype, ".jpg")
        name += ext
    return name

def extract_and_save_images(msg: Message) -> Tuple[List[str], Path]:
    """
    Extract inline image parts from the USPS digest email and save them under
    /config/www/minimail/usps/YYYY-MM-DD/. Return (public_urls, folder_path).
    Public URLs are /local/minimail/usps/YYYY-MM-DD/<file>.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = ROOT / today
    out_dir.mkdir(parents=True, exist_ok=True)

    urls: List[str] = []
    idx = 0

    for part in msg.walk():
        ctype = (part.get_content_type() or "").lower()
        if ctype not in _IMG_CTYPES:
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            # Handle rare base64-as-text payloads
            raw = part.get_payload(decode=False) or ""
            try:
                payload = base64.b64decode(raw, validate=False)
            except Exception:
                continue

        fname = _pick_filename(part, idx)
        idx += 1

        dest = out_dir / fname
        try:
            with open(dest, "wb") as f:
                f.write(payload)
        except Exception:
            # Skip broken image parts silently
            continue

        # HA will serve /config/www as /local
        public = f"/local/minimail/usps/{today}/{fname}"
        urls.append(public)

    return urls, out_dir
