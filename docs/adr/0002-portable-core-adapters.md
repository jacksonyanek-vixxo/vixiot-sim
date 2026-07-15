# ADR 0002: Portable Core + Platform Adapters

## Status
Accepted

## Context
Core simulation logic (equipment physics, irregularities, aggregation, scheduling) must be unit-testable under CPython with pytest, yet run unchanged on MicroPython ESP32-S3 firmware. Hardware-specific code (WiFi, umqtt, flash, NTP) must not leak into the core.

## Decision
Split the codebase into:
- **`core/`** — pure Python, no hardware imports; runs under CPython and MicroPython.
- **`firmware/platform/`** — thin adapters for WiFi, MQTT, flash storage, and clock.
- **`tools/virtual_device.py`** — CPython runner wiring core + paho-mqtt for end-to-end demo without hardware.

## Consequences
- pytest covers all business logic without an ESP32.
- Firmware `main.py` is a thin orchestration loop calling core APIs through adapters.
- Adapter interfaces are minimal (connect, publish, read/write config, now_iso) to keep MicroPython footprint small.
