# ADR 0001: MQTT + JSON Transport

## Status
Accepted

## Context
The simulator must publish telemetry from an ESP32-S3 (MicroPython) to a local receiving layer. Options considered:
- **HTTP REST** — simple but polling-oriented, higher overhead per reading, no native pub/sub or retained state.
- **Sparkplug B (protobuf over MQTT)** — industrial-grade but heavy protobuf stack unavailable on MicroPython without significant porting effort.
- **MQTT + JSON** — lightweight pub/sub, retained messages for birth/LWT, JSON parseable everywhere.

## Decision
Use MQTT (Mosquitto broker) with pragmatic custom JSON payloads on topic hierarchy `vixiot/{device_id}/…`.

## Consequences
- Self-contained Docker broker + Python paho-mqtt sink.
- JSON-schema validation at the sink; no protobuf code generation on device.
- QoS 1 for telemetry and state; retained birth/LWT on `state` topic.
- Payload size is larger than protobuf but acceptable at 30 s publish intervals.
