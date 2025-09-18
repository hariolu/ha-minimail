# 📬 Home Assistant MiniMail

Custom integration for Home Assistant that polls an **IMAP mailbox** and exposes structured **mail & package sensors**.  
Designed for forwarding Amazon, USPS and other delivery notifications into Home Assistant — great for dashboards, digests, and Telegram bots 🐺.

---
- **Amazon parser**:
  - Extracts item list, ETA, shipment ID, order ID, progress link.
  - Tracks events (`Shipped`, `Out for delivery`, `Delivered`).
- **USPS parser**:
  - Digest: number of mailpieces & packages expected today, senders, dashboard link.
  - Delivered emails: last delivered date & status.
  - 
## ✨ Features
- 📥 **IMAP fetcher** — connect to any mailbox folder via SSL/TLS.  
- 🔍 **Flexible search** — supports custom IMAP queries (`ALL`, `UNSEEN`, …).  
- ⏱ **Configurable polling interval** (default: 90s).  
- 🧩 **Sender filters** — restrict which rules to apply.  
- 🔄 **Fetch limit** — control how many emails to scan per update.  
- 🛡 Safe & defensive parsers — tolerate missing parts and messy headers.

---

## 🛠 Example Use Cases
- 🤖 **Telegram/Discord bots** — auto-post Amazon shipment status or USPS digest.  
- 📊 **Dashboards** — display today’s expected mail & package list.  
- 🚨 **Notifications** — push alert when USPS mail is delivered.  
- 📅 **Automations** — trigger lights or sounds when Amazon order goes “Out for delivery”.  

---

## 📂 Example Configuration (sensors.yaml)

### Mini config
```yaml
- platform: minimail
  host: imap.example.com
  port: 993
  ssl: true
  username: myuser@example.com
  password: mysecret
```

---

### Full config
```yaml
- platform: minimail
  host: imap.example.com
  port: 993
  ssl: true
  username: myuser@example.com
  password: mysecret
  folder: "bot"              # mailbox folder with forwarded emails
  search: "ALL"              # IMAP search query
  fetch_limit: 30            # how many emails to scan per poll
  update_interval: 90        # seconds
  sender_filters:            # restrict rules (optional)
    - usps
    - amazon.com
```

---

## 📡 Exposed Sensors

### USPS
- `sensor.minimail_usps_mailpieces_expected_today`
- `sensor.minimail_usps_packages_expected_today`
- `sensor.minimail_usps_mail_from`
- `sensor.minimail_usps_packages_from`
- `sensor.minimail_usps_last_delivered`
- `sensor.minimail_usps_scans`

### Amazon
- `sensor.minimail_amazon_items`
- `sensor.minimail_amazon_eta`
- `sensor.minimail_amazon_last_event`
- `sensor.minimail_amazon_track_url`
- `sensor.minimail_amazon_order_id`
- `sensor.minimail_amazon_shipment_id`
- `sensor.minimail_amazon_package_index`

---

## ⚙️ How it works
- Component runs a **MailCoordinator** (`DataUpdateCoordinator`) on schedule.  
- `imap_client.py` fetches and decodes messages.  
- Each rule in `rules/` parses messages into structured dicts.  
- Sensors in `sensor_*.py` expose those dicts as Home Assistant entities.  

---

## 📜 License
Released under the **MIT License**.  
Free to use, share and modify — just keep attribution ⭐.
