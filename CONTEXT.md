# VixIoT Simulator — Domain Glossary

## Asset / Machine
A physical piece of equipment represented by a single `device_id`. In this project, one ESP32-S3 board simulates one super-automatic espresso machine.

## Equipment Profile
The set of telemetry channels, units, healthy baseline ranges, machine states, and cumulative counters that define how a specific machine type behaves. Implemented in `core/espresso.py` for Schaerer-style super-automatics.

## Telemetry
A JSON payload published on `vixiot/{device_id}/telemetry` containing aggregated metrics, counters, machine state, and active faults for a publish window.

## Metric
A single measured signal (e.g. `brew_boiler_temp`) with a current `value`, optional window aggregates (`min`, `max`, `mean`), `unit`, and `quality` (`good`, `suspect`, `bad`, `missing`).

## Sample vs Publish Interval
The device samples sensors at `sample_interval_ms` (fast, e.g. 1 s) and publishes aggregated telemetry at `publish_interval_s` (slow, e.g. 30 s). Edge processing happens between the two.

## Window / Aggregate
The time span between publishes. Each metric in a telemetry message reflects min/max/mean/last over all samples collected in that window.

## Report-by-Exception (RBE)
An immediate telemetry publish triggered by a fault appearance, threshold breach, or significant state change — without waiting for the next scheduled publish interval.

## Store-and-Forward
When the MQTT broker is unreachable, telemetry records are buffered locally (flash on device, memory in virtual runner) and replayed in order once connectivity returns.

## Irregularity
A deviation from healthy baseline behavior. Two layers:
- **Failure Pattern** — correlated, domain-realistic degradation (scaling, grinder wear, pump degradation, clogged group, heater degradation).
- **Signal Anomaly** — generic per-channel perturbations (spike, drift, stuck, dropout, out_of_range, noise).

## PM Band
Preventive-maintenance threshold bands tied to counters (e.g. descale due at 500 shots, burr replacement at 15 000 shots). Exposed in counters and may surface as advisory faults.

## Counter
Monotonically increasing operational tallies: `total_shots`, `shots_since_descale`, `operating_hours`.

## Fault
A named active degradation condition (e.g. `scaling`) listed in `active_faults`. Faults drive report-by-exception and sink-side work-order creation.

## Sink
The Python receiving layer (`sink/subscriber.py`) that subscribes to MQTT topics, validates JSON against schema, persists records to JSONL, and tracks device online/offline via birth/LWT.

## Downlink Command
A JSON message on `vixiot/{device_id}/cmd` (e.g. `set_config`) sent by the sink CLI to reconfigure the device at runtime. The device applies, persists to `config.json`, and acks on `cmd/ack`.

## Birth / LWT
MQTT birth message (retained `online` on `state` topic at connect) and Last-Will-and-Testament (`offline` on disconnect). Used by the sink for presence tracking.

## Quality
Per-metric data-quality flag reflecting sensor health: `good`, `suspect` (anomaly applied), `bad` (out of range or stuck), `missing` (dropout).

## Work Order
A maintenance ticket created by the sink when a device reports a new fault. One open WO per `(device_id, fault)`; closed when the fault clears from `active_faults`.
