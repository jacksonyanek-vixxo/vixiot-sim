# VixIoT Espresso Machine IoT Simulator

ESP32-S3 MicroPython firmware simulates a Schaerer-style super-automatic espresso machine, publishing JSON telemetry over MQTT. A portable Python core runs on-device or under CPython for testing and demo.

## Architecture

- **`core/`** — Portable simulation (equipment profile, irregularities, aggregation, scheduler, buffer)
- **`firmware/`** — MicroPython entry point + platform adapters (WiFi, MQTT, flash, NTP)
- **`sink/`** — Python MQTT subscriber (validate, JSONL store, work orders) + config CLI
- **`deploy/`** — Mosquitto Docker Compose
- **`tools/virtual_device.py`** — CPython end-to-end demo without hardware

### MQTT Topics

| Topic | Purpose |
|-------|---------|
| `vixiot/{device_id}/telemetry` | Aggregated telemetry + exceptions |
| `vixiot/{device_id}/state` | Birth (online) + LWT (offline), retained |
| `vixiot/{device_id}/cmd` | Downlink `set_config` |
| `vixiot/{device_id}/cmd/ack` | Config apply result |
| `vixiot/{device_id}/workorder` | Work orders (sink publishes) |

See [CONTEXT.md](CONTEXT.md) and [docs/adr/](docs/adr/) for domain glossary and decisions.

## Quick Start (Demo)

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start Mosquitto broker

```bash
cd deploy && docker compose up -d
```

### 3. Start the sink (terminal 1)

```bash
python sink/subscriber.py --broker localhost
```

### 4. Run virtual device (terminal 2)

```bash
python tools/virtual_device.py --broker localhost --fast
```

### 5. Push config / enable scaling (terminal 3)

```bash
# Mild: enable scaling only
python sink/cli.py --broker localhost --enable-scaling --publish-interval-s 5

# Aggressive: all faults + anomalies, 100ms sample / 5s publish
python sink/cli.py --broker localhost --aggressive
```

The sink will open a work order when `scaling` appears in `active_faults` and close it when the fault clears.

## Tests

```bash
pytest tests/ -v
```

## Hardware (ESP32-S3)

1. Flash MicroPython for ESP32-S3.
2. Copy `core/`, `firmware/main.py`, `firmware/boot.py`, `firmware/config.json`, and `firmware/platform/` to the device.
3. Copy `firmware/secrets.example.py` to `secrets.py` and set WiFi/MQTT credentials.
4. Run `main.py` on boot.

Config persists to `config.json` on flash; downlink commands via `sink/cli.py` apply at runtime.

## Data outputs

- `sink/data/telemetry.jsonl` — validated telemetry records
- `sink/data/state.jsonl` — online/offline events
- `sink/data/workorders.jsonl` — work order create/close events
