# custom_components/minimail/imap_client.py
from __future__ import annotations

import imaplib
import ssl
import email
from email.message import Message
from typing import Any, Dict
from homeassistant.core import HomeAssistant

from .const import (
    CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD, CONF_FOLDER,
    CONF_SSL, CONF_SEARCH, CONF_FETCH_LIMIT, DEFAULT_SEARCH, DEFAULT_FETCH_LIMIT,
)
from .imap_client_amazon import handle_amazon
from .imap_client_usps import handle_usps_digest, handle_usps_delivered


def process_message(parsed: Dict[str, Any], data: Dict[str, Any], flags: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Route a parsed message to USPS/Amazon handlers.

    IMPORTANT:
    - We now keep two independent flags:
        flags['got_usps_digest'], flags['got_usps_delivered']
      so Delivered and Digest can BOTH merge data in one pass.
    """
    msg: Message = parsed.get("_message")
    # use casefold() for more robust Unicode-insensitive matching than lower()
    subj = (parsed.get("subject") or "").casefold()
    frm = (parsed.get("from") or "").casefold()
    if not msg:
        return data, flags

    # Amazon
    if "amazon" in frm or "shipment-tracking@amazon" in frm:
        amazon = data.setdefault("amazon", {})
        amazon, got = handle_amazon(msg, amazon)
        if got:
            data["amazon"] = amazon
        return data, flags

    # USPS?
    # USPS sender addresses appear in many variants, e.g. 'USPS Informed Delivery',
    # 'USPSInformedDelivery@informeddelivery.usps.com', forwarding aliases, etc.
    is_usps = (
        "informeddelivery" in frm
        or "email.informeddelivery.usps.com" in frm
        or "usps informed delivery" in frm
        or "uspsinformeddelivery@" in frm
        or ("usps" in frm and "delivery" in frm)
    )

    if is_usps:
        # USPS Delivered
        if (
            "your mail was delivered" in subj
            or "mail delivery notification" in subj
            or "mailpiece delivered" in subj
            or "mail piece delivered" in subj
            or subj.startswith("delivered")
            or subj.endswith("delivered")
        ):
            # take ONLY the first Delivered (loop is newest → older)
            if not flags.get("got_usps_delivered"):
                usps = data.setdefault("usps", {})
                usps, _ = handle_usps_delivered(msg, usps)
                data["usps"] = usps
                flags["got_usps_delivered"] = True
            return data, flags

        # USPS Daily Digest
        if ("daily digest" in subj) or ("ready to view" in subj) \
           or ("informed delivery" in subj) or ("coming to you soon" in subj):
            if not flags.get("got_usps_digest"):
                usps = data.setdefault("usps", {})
                usps, _ = handle_usps_digest(msg, usps)
                data["usps"] = usps
                flags["got_usps_digest"] = True
            return data, flags

    return data, flags


class ImapClient:
    def __init__(self, hass: HomeAssistant, conf: Dict[str, Any]) -> None:
        self.hass = hass
        self.conf = conf
        self._data: Dict[str, Any] = {
            "usps": {},
            "amazon": {},
        }
        self._flags: Dict[str, Any] = {}

    def seed(self, snapshot: Dict[str, Any]) -> None:
        """Warm-start internal state from a persisted snapshot (USPS/Amazon only)."""
        try:
            if isinstance(snapshot, dict):
                self._data = {
                    "usps": dict((snapshot.get("usps") or {})),
                    "amazon": dict((snapshot.get("amazon") or {})),
                }
        except Exception:
            # Best-effort; ignore seeding errors
            pass

    def _fetch_sync(self) -> Dict[str, Any]:
        """
        Blocking IMAP fetch (runs in executor). Returns updated data dict.
        """
        host = self.conf.get(CONF_HOST)
        port = int(self.conf.get(CONF_PORT) or 993)
        user = self.conf.get(CONF_USERNAME)
        pwd = self.conf.get(CONF_PASSWORD)
        folder = self.conf.get(CONF_FOLDER) or "INBOX"
        use_ssl = bool(self.conf.get(CONF_SSL, True))
        search = self.conf.get(CONF_SEARCH) or DEFAULT_SEARCH
        fetch_limit = int(self.conf.get(CONF_FETCH_LIMIT, DEFAULT_FETCH_LIMIT) or DEFAULT_FETCH_LIMIT)

        if not host or not user or not pwd:
            return self._data

        # connect
        if use_ssl:
            ctx = ssl.create_default_context()
            M = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
        else:
            M = imaplib.IMAP4(host, port)

        try:
            M.login(user, pwd)
            typ, _ = M.select(folder, readonly=True)
            if typ != "OK":
                try:
                    M.logout()
                finally:
                    return self._data

            typ, ids = M.search(None, search)
            if typ != "OK":
                M.close()
                M.logout()
                return self._data

            all_ids = (ids[0] or b"").split()
            if not all_ids:
                M.close()
                M.logout()
                return self._data

            pick = all_ids[-fetch_limit:]

            # Fresh pass each poll:
            # - start from the last known payload (shallow copy per section)
            # - but RESET per-pass routing flags so newer USPS letters are parsed
            data = {
                "usps": dict((self._data.get("usps") or {})),
                "amazon": dict((self._data.get("amazon") or {})),
            }
            flags = {
                "got_usps_digest": False,
                "got_usps_delivered": False,
            }

            # Newest first
            for uid in reversed(pick):
                typ, parts = M.fetch(uid, "(RFC822)")
                if typ != "OK" or not parts or parts[0] is None:
                    continue
                raw = parts[0][1]
                if not raw:
                    continue

                try:
                    msg: Message = email.message_from_bytes(raw)
                except Exception:
                    continue

                try:
                    from_hdr = str(email.header.make_header(email.header.decode_header(msg.get("From", "")))) if msg.get("From") else (msg.get("From") or "")
                except Exception:
                    from_hdr = msg.get("From", "") or ""

                try:
                    subj_hdr = str(email.header.make_header(email.header.decode_header(msg.get("Subject", "")))) if msg.get("Subject") else (msg.get("Subject") or "")
                except Exception:
                    subj_hdr = msg.get("Subject", "") or ""

                parsed = {"from": from_hdr, "subject": subj_hdr, "_message": msg}
                data, flags = process_message(parsed, data, flags)

            # Save parsed data; flags are per-pass, do not carry them over.
            self._data = data
            # keep flags only if ever needed for future diagnostics, but
            # ensure next pass starts clean
            self._flags = {}

            try:
                M.close()
            except Exception:
                pass
            M.logout()
            return self._data

        except Exception:
            try:
                M.logout()
            except Exception:
                pass
            return self._data

    async def fetch(self) -> Dict[str, Any]:
        """
        Run blocking IMAP fetch in executor and return updated data dict.
        """
        return await self.hass.async_add_executor_job(self._fetch_sync)
