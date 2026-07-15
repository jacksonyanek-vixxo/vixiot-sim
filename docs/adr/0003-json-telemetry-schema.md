# ADR 0003: Custom JSON Telemetry Schema + Versioning

## Status
Accepted

## Context
Telemetry payloads need a documented, validatable shape. Alternatives:
- **Homie convention** — MQTT-native discovery but opinionated topic layout and limited aggregate support.
- **Sparkplug JSON** — tied to Sparkplug lifecycle; overkill for a single-machine simulator.
- **Custom JSON with `schema_version`** — pragmatic, self-describing, JSON-schema validated at sink.

## Decision
Define a custom JSON telemetry schema (version `1.0`) with fields: `schema_version`, `device_id`, `equipment_type`, `timestamp`, `seq`, `event`, `window`, `metrics`, `counters`, `state`, `active_faults`. Maintain `sink/schema/telemetry.schema.json` and validate on ingest.

## Consequences
- Schema evolution via `schema_version` bump; sink rejects unknown major versions.
- Metrics carry optional window aggregates and per-channel `quality`.
- Commands (`set_config`) use a separate informal schema documented in CONTEXT.md and ADR 0001.
