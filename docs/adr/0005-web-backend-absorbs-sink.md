# ADR 0005: Web backend absorbs the sink

## Status

Accepted

## Context

The dashboard needs validated telemetry, online state, work orders, config
acknowledgements, and an MQTT command path. Running an independent browser
subscriber would duplicate validation and work-order behavior, while connecting
the browser directly to MQTT would expose broker credentials and couple the UI
to transport details.

## Decision

Extract MQTT subscription, schema validation, JSONL persistence, work-order
management, in-memory device history, and `set_config` publishing into
`sink/hub.py`.

The FastAPI process owns one hub and bridges paho-mqtt's network thread to
asyncio. REST endpoints serve snapshots, history, work orders, and commands;
WebSocket events carry live updates and initial backfill. The browser is a
no-build static application and never connects to MQTT.

`sink/subscriber.py` remains a thin headless wrapper around the same hub, so
local Mosquitto and HiveMQ Cloud workflows keep their existing behavior.

## Consequences

- One backend process owns MQTT when the dashboard is running.
- Headless and web modes share validation, persistence, and work-order logic.
- Per-device history is limited to 500 telemetry records and resets on restart.
- Browser clients need no broker credentials.
- The web server has no application authentication and binds to localhost by
  default; exposing it on another interface requires an appropriate security
  layer.
