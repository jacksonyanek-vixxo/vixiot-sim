# ADR 0006: Mastrena-style event stream

## Status

Accepted

## Context

Fleet exports for Mastrena II machines include a discrete **Error_Events** log
and an **EventMaster** catalog (event number, name, severity, category, module).
The simulator already emits windowed sensor telemetry and simulation faults, but
those concepts do not map cleanly onto the event log model.

We needed to decide whether to fold events into telemetry, generate offline
exports, or publish a new live record type; how faithful the catalog should be;
and how events relate to the existing fault/irregularity system.

## Decision

1. **Separate MQTT topic** — publish one JSON message per occurrence on
   `vixiot/{device_id}/event` with its own schema. Telemetry stays unchanged.

2. **Full real catalog** — embed all 73 EventMaster entries verbatim in portable
   `core/events_catalog.py`, plus a raise→clear pairing map derived from
   Mastrena naming conventions.

3. **Orthogonal to faults** — keep `active_faults` in telemetry as-is. Add a
   hybrid `EventEngine` driven by machine state, PM counters, low-rate
   stochastic Info events, and optional fault triggers (e.g. sustained
   `pump_degradation` → `WaterFlowError`).

4. **Sink integration** — validate events, persist to `events.jsonl`, stream
   over WebSocket, and open/close work orders for Error/Fatal stateful raises
   keyed by `(device_id, pairing group, module)`.

5. **Configuration** — add an `events` block to device config (global enable,
   per-category rate multipliers, optional inject list) applied via existing
   `set_config`.

## Consequences

- Devices may publish both telemetry and events; sinks must subscribe to both.
- Event work orders coexist with fault work orders using different dedupe keys.
- Warning/Info events never open work orders; dashboard shows them in an Event
  Feed for operator visibility.
- Product Results and Counter snapshot exports remain out of scope for now.
