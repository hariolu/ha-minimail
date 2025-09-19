Repository: ha-minimail — MiniMail Home Assistant integration

Purpose
- Help an AI coding agent become productive quickly: explain architecture, key files, dataflow, and project-specific conventions.

Big picture
- This is a Home Assistant custom integration that polls IMAP mailboxes and exposes sensors for USPS and Amazon delivery data.
- Core runtime flow: `sensor.py` constructs an `ImapClient` -> `MailCoordinator` -> coordinator periodically calls `ImapClient.fetch()` -> `imap_client.py` fetches messages and routes each message via `process_message()` -> rules in `minimail/rules/` parse messages -> sensors in `sensor_amazon.py` and `sensor_usps.py` expose coordinator data.

Key files and responsibilities (refer to these when making changes)
- `minimail/imap_client.py`: IMAP connection, message fetch loop, message routing via `process_message()`.
- `minimail/imap_client_amazon.py`, `minimail/imap_client_usps.py`: thin adapters that call rule parsers and merge results.
- `minimail/rules/*.py`: parsers that produce structured dicts (e.g., `parse_amazon_email`, `parse_usps_digest`). Prefer editing/adding rules here for new sender formats.
- `minimail/coordinator.py`: `MailCoordinator` subclass of `DataUpdateCoordinator` — uses `update_interval` from sensor config.
- `minimail/sensor*.py`: lightweight CoordinatorEntity sensors exposing parts of the parsed dict. Sensor factories are exported as `AMAZON_ENTITIES` and `USPS_ENTITIES`.
- `minimail/const.py`: central config keys and defaults used across modules.
- `manifest.json`: integration metadata — keep `version` and `requirements` up to date when adding external deps.

Patterns and conventions
- Parsers return plain dicts (not custom classes). Keys used by sensors are documented in `sensor_amazon.py` and `sensor_usps.py` (e.g., `amazon: {subject,event,items,track_url,...}` and `usps: {mail_expected, pkgs_expected, mail_from, pkgs_from, buckets,...}`).
- Imap client logic keeps `self._data` and `self._flags` between fetches — handlers merge into these dicts rather than replacing everything. Preserve this merging behavior when changing handlers.
- Robust defensive decoding: header decode calls are guarded by try/except — follow that pattern when reading email headers/bodies.
- Rules live under `minimail/rules/`. Adapters (`imap_client_amazon.py`/`imap_client_usps.py`) try those first then fall back to legacy locations; adding a new parser should go under `rules/`.
- Tests: none included. When adding functionality, add small, focused unit tests for parser functions (e.g., `parse_usps_digest`) and validate keys expected by sensors.

Developer workflow / commands
- This is a Python Home Assistant custom component. Typical local validation steps:
  - Static checks: run `python -m pip install -r requirements.txt` if you add dependencies and run your linter locally.
  - Manual testing: copy the `minimail/` folder into Home Assistant `custom_components/minimail/` and restart Home Assistant (or use the dev container / test instance).
  - Use the integration via `sensors.yaml` sample in `README.md` to exercise end-to-end behavior.

Integration points & external dependencies
- IMAP: uses Python stdlib `imaplib` + `ssl` to connect. No external IMAP dependencies in `manifest.json`.
- Email parsing: uses stdlib `email` package. Parsers may write files to Home Assistant `www` dir (USPS image extraction uses `HASS_CONFIG` env var). Be careful when adding file operations — follow HA sandboxing and config paths.

Editing guidance for common tasks
- Add a new sender parser: implement `parse_*_email(msg: Message) -> Dict` in `minimail/rules/`, then update/verify adapters are importing it. Keep parsers pure (no side effects) — adapters handle merging.
- Change coordinator behavior: modify `minimail/coordinator.py` but keep return type `Dict[str, Any]` for compatibility with sensors.
- Add sensor: create a new class in `sensor_amazon.py` or `sensor_usps.py` inheriting from `_Base`, add to the exported factory list (`AMAZON_ENTITIES`/`USPS_ENTITIES`) and reference keys that existing parsers produce.

Examples from this repo
- Amazon parser produces: `{'subject','headline','event','items','track_url','order_id','shipment_id','package_index','eta'}` (`minimail/rules/amazon.py`).
- USPS digest returns `mail_expected`, `pkgs_expected`, `mail_from` (not deduped), `pkgs_from`, `buckets`, and `mail_images` (`minimail/rules/usps_digest.py`) and adapters expose these under `usps`.

What not to change lightly
- The merging semantics in `imap_client.py` (`self._data` + `self._flags`) — sensors and adapters rely on incremental updates.
- Sensor unique IDs (`_attr_unique_id = f"{namespace}_{key}"`) — changing format breaks users' entity registry.
- `manifest.json` keys: update carefully when bumping versions or adding runtime requirements.

When you need more context
- Inspect `sensor.py` → `_ensure_coordinator_from_platform` path to see how config is passed into `ImapClient`.
- Look in `README.md` for example `sensors.yaml` and expected sensor entity IDs.

If anything here is unclear, tell me which area you'd like expanded (parsers, sensors, IMAP fetch flow, or tests) and I will iterate.
