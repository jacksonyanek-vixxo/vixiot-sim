# VixIoT Espresso Machine IoT Simulator

ESP32-S3 MicroPython firmware simulates a Schaerer-style super-automatic espresso machine, publishing JSON telemetry over MQTT. A portable Python core runs on-device or under CPython for testing and demo.

## Architecture

- **`core/`** — Portable simulation (equipment profile, irregularities, aggregation, scheduler, buffer)
- **`firmware/`** — MicroPython entry point + platform adapters (WiFi, MQTT, flash, NTP, LED)
- **`sink/`** — Python MQTT subscriber (validate, JSONL store, work orders) + config CLI
- **`deploy/`** — Local Mosquitto Docker Compose (optional when using cloud broker)
- **`scripts/deploy.sh`** — Deploy firmware to ESP32-S3 via `mpremote`
- **`tools/virtual_device.py`** — CPython end-to-end demo without hardware

### MQTT Topics

| Topic | Purpose |
|-------|---------|
| `vixiot/{device_id}/telemetry` | Aggregated telemetry + exceptions |
| `vixiot/{device_id}/event` | Discrete Mastrena-style catalog events (raise/clear/momentary) |
| `vixiot/{device_id}/state` | Birth (online) + LWT (offline), retained |
| `vixiot/{device_id}/cmd` | Downlink `set_config` |
| `vixiot/{device_id}/cmd/ack` | Config apply result |
| `vixiot/{device_id}/workorder` | Work orders (sink publishes) |

See [CONTEXT.md](CONTEXT.md) and [docs/adr/](docs/adr/) for domain glossary and decisions.

## Quick Start

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Choose **local Mosquitto** (same LAN) or **HiveMQ Cloud** (corporate WiFi / VLAN split).

---

### Option A — Local broker (Docker)

**Terminal 1 — broker**

```bash
cd deploy && docker compose up -d
```

**Terminal 2 — sink**

```bash
python sink/subscriber.py --broker localhost
```

**Terminal 3 — virtual device (no hardware)**

```bash
python tools/virtual_device.py --broker localhost --fast
```

**Terminal 4 — push config**

```bash
python sink/cli.py --broker localhost --aggressive
```

Device `secrets.py` for local use:

```python
MQTT_BROKER = "192.168.x.x"   # laptop IP on same LAN as ESP — not localhost
MQTT_PORT = 1883
MQTT_SSL = False
MQTT_USER = None
MQTT_PASSWORD = None
```

---

### Option B — HiveMQ Cloud (recommended on corporate WiFi)

When the ESP and laptop are on different VLANs (same SSID, different subnets), both connect to a cloud broker over the internet. See [ADR 0004](docs/adr/0004-hivemq-cloud-broker.md).

**1. Create a cluster** at [console.hivemq.cloud](https://console.hivemq.cloud/) and note URL, username, and password.

**2. Device credentials** — copy [firmware/secrets.example.py](firmware/secrets.example.py) to `secrets.py`:

```python
WIFI_SSID = "your-ssid"
WIFI_PASSWORD = "your-password"

MQTT_BROKER = "YOUR_CLUSTER.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_SSL = True
MQTT_USER = "your-hivemq-username"
MQTT_PASSWORD = "your-hivemq-password"
```

**3. Deploy to ESP32-S3**

```bash
./scripts/deploy.sh /dev/cu.usbmodem1101
```

**4. Run sink** (same broker + credentials)

```bash
python sink/subscriber.py \
  --broker YOUR_CLUSTER.s1.eu.hivemq.cloud \
  --port 8883 --tls \
  --user YOUR_USER --password YOUR_PASS
```

**5. Push config downlink**

```bash
python sink/cli.py \
  --broker YOUR_CLUSTER.s1.eu.hivemq.cloud \
  --port 8883 --tls \
  --user YOUR_USER --password YOUR_PASS \
  --aggressive
```

Optional shell shortcuts:

```bash
export HIVEMQ_BROKER=YOUR_CLUSTER.s1.eu.hivemq.cloud
export HIVEMQ_USER=your-user
export HIVEMQ_PASS=your-pass

python sink/subscriber.py --broker "$HIVEMQ_BROKER" --port 8883 --tls \
  --user "$HIVEMQ_USER" --password "$HIVEMQ_PASS"
```

---

### What to expect

- Sink prints `[state] espresso-001 -> online` then `[telemetry]` every ~30s
- Work orders open/close when `active_faults` change (with `--aggressive`)
- Data files: `sink/data/telemetry.jsonl`, `state.jsonl`, `workorders.jsonl`

## Tests

```bash
pytest tests/ -v
```

## Web UI

The FastAPI dashboard replaces the headless sink when it is running: it owns the
MQTT connection, persists the same JSONL records, manages work orders, and
streams live data to the browser. Do not run `sink/subscriber.py` at the same
time unless you intentionally want a second sink.

For local Mosquitto:

```bash
uvicorn sink.app:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The dashboard discovers
devices from wildcard MQTT topics and provides live charts, status, faults,
work orders, and config/fault-injection controls.

For HiveMQ Cloud, configure the MQTT connection through environment variables:

```bash
export VIXIOT_BROKER=YOUR_CLUSTER.s1.eu.hivemq.cloud
export VIXIOT_MQTT_PORT=8883
export VIXIOT_MQTT_TLS=true
export VIXIOT_MQTT_USER=YOUR_USER
export VIXIOT_MQTT_PASSWORD=YOUR_PASSWORD
uvicorn sink.app:app --host 127.0.0.1 --port 8000
```

The equivalent CLI form supports the same broker options:

```bash
python -m sink.app --broker localhost --port 1883 --web-port 8000
```

The web server binds only to `127.0.0.1` by default and has no authentication.
See [ADR 0005](docs/adr/0005-web-backend-absorbs-sink.md).

## Hardware (ESP32-S3 / Seeed XIAO)

### One-time setup

1. Flash [MicroPython for ESP32-S3](https://micropython.org/download/ESP32_GENERIC_S3/) (Seeed XIAO build).
2. Copy `firmware/secrets.example.py` → `secrets.py` and set WiFi + MQTT (local or HiveMQ).
3. Deploy everything:

```bash
./scripts/deploy.sh /dev/cu.usbmodem1101
```

The script copies `core/`, platform adapters (`wifi.py`, `mqtt.py`, `led.py`, …), `secrets.py`, and `main.py` last. Close Thonny/other serial apps first.

### Status LED (orange, GPIO 21)

| Pattern | State |
|---------|--------|
| 5 fast blinks at boot | Self-test |
| Slow pulse | WiFi connecting |
| Double blink | WiFi connected |
| Medium blink | MQTT connecting |
| Brief flash every ~2s | Running |
| Fast blink | Active fault |
| Long on / short off | WiFi/MQTT error |

The **red LED** near USB is charge/power only — not firmware status.

Configure in `secrets.py`: `LED_PIN`, `LED_ACTIVE_LOW`, `LED_ENABLED`.

### WiFi troubleshooting

MicroPython on ESP32 requires STA reset before scan/connect. If WiFi fails, use REPL steps in [firmware/wifi_debug.py](firmware/wifi_debug.py) or redeploy — `firmware/platform/wifi.py` handles this automatically.

### Config downlink

Runtime changes via MQTT (`sink/cli.py`) persist to `config.json` on flash.

## Data outputs

- `sink/data/telemetry.jsonl` — validated telemetry records
- `sink/data/state.jsonl` — online/offline events
- `sink/data/workorders.jsonl` — work order create/close events
