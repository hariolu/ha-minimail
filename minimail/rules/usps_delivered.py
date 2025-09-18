# file: custom_components/minimail/usps_delivered.py
# Always code in English; comments in English.

import re
import email
from email.message import Message
from datetime import datetime
from typing import Dict, Any, Optional

MONTHS = {
    "Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
    "May": "May", "Jun": "June", "Jul": "July", "Aug": "August",
    "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December",
}

SUBJECT_RX = re.compile(r"Your Mail Was Delivered\s+\w+,\s+([A-Za-z]{3})\s+(\d{1,2})", re.I)

def _parse_subject_date(subj: str) -> Optional[Dict[str, Any]]:
    """
    Subject usually looks like:
    'Your Mail Was Delivered Fri, Sep 12'
    We map 'Sep' -> 'September' and keep day number.
    """
    if not subj:
        return None
    m = SUBJECT_RX.search(subj)
    if not m:
        return None
    mon_abbr, day_s = m.group(1), m.group(2)
    mon_full = MONTHS.get(mon_abbr.capitalize(), mon_abbr)
    day = int(day_s)
    # We do not guess the year from subject; fallback to now().year for labeling only.
    year = datetime.now().year
    return {
        "month_abbr": mon_abbr.capitalize(),
        "month": mon_full,
        "day": day,
        "year": year,
        "label": f"today, {mon_full} {day}!",  # Friendly label for the bot message
    }

def parse_usps_delivered(msg: Message) -> Dict[str, Any]:
    """
    Parse USPS 'Your Mail Was Delivered' email into a tiny structure for HA.

    Returns:
        {
          "subject": "...",
          "delivered": True,
          "date_label": "today, September 12!",
          "month": "September",
          "day": 12,
          "year": 2025,            # best-effort
          "dashboard_url": "https://informeddelivery.usps.com/portal/dashboard"
        }
    """
    try:
        subj = str(email.header.make_header(email.header.decode_header(msg.get("Subject", "")))).strip()
    except Exception:
        subj = msg.get("Subject", "") or ""

    info = _parse_subject_date(subj) or {}

    # Stable default USPS dashboard (we also let caller overwrite from existing usps block)
    dash = "https://informeddelivery.usps.com/portal/dashboard"

    out: Dict[str, Any] = {
        "subject": subj,
        "delivered": True,
        "date_label": info.get("label", "").strip() or "",
        "month": info.get("month", ""),
        "day": info.get("day", 0),
        "year": info.get("year", 0),
        "dashboard_url": dash,
    }
    return out
