# ADR 0004: HiveMQ Cloud for cross-VLAN MQTT

## Status

Accepted

## Context

On corporate WiFi (e.g. `PG_VIX`), employee laptops and IoT devices often land on different VLANs with inter-client filtering. A local Mosquitto broker on the laptop is unreachable from the ESP32 even when both use the same SSID.

## Decision

Support **HiveMQ Cloud** (or any MQTT broker reachable over the internet) using **TLS on port 8883** with username/password authentication.

- Device: `secrets.py` fields `MQTT_BROKER`, `MQTT_PORT`, `MQTT_SSL`, `MQTT_USER`, `MQTT_PASSWORD`
- Firmware: `umqtt.simple` with `ssl=True` and `ssl_params` (`CERT_NONE` on ESP32 — no bundled CA store)
- Sink/CLI: paho-mqtt with `certifi` CA bundle via `--tls`, `--user`, `--password`

## Consequences

- ESP and laptop no longer need same LAN/VLAN; both egress to cloud broker
- TLS cert verification is relaxed on-device (demo trade-off); sink verifies normally via `certifi`
- Cloud broker credentials must be kept in gitignored `secrets.py`, never committed
