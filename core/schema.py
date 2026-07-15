"""JSON telemetry, state, and command payload builders."""

from core.config import EQUIPMENT_TYPE, SCHEMA_VERSION


def build_telemetry(
    device_id,
    seq,
    timestamp,
    metrics,
    counters,
    state,
    active_faults,
    window_start=None,
    window_end=None,
    sample_count=0,
    event="telemetry",
):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "device_id": device_id,
        "equipment_type": EQUIPMENT_TYPE,
        "timestamp": timestamp,
        "seq": seq,
        "event": event,
        "metrics": metrics,
        "counters": {
            "total_shots": int(counters.get("total_shots", 0)),
            "shots_since_descale": int(counters.get("shots_since_descale", 0)),
            "operating_hours": round(float(counters.get("operating_hours", 0)), 1),
        },
        "state": state,
        "active_faults": list(active_faults or []),
    }
    if window_start and window_end:
        payload["window"] = {
            "start": window_start,
            "end": window_end,
            "sample_count": sample_count,
        }
    return payload


def build_state_message(device_id, status, timestamp):
    return {
        "schema_version": SCHEMA_VERSION,
        "device_id": device_id,
        "status": status,
        "timestamp": timestamp,
    }


def build_cmd_ack(device_id, success, message="", config_applied=None):
    ack = {
        "schema_version": SCHEMA_VERSION,
        "device_id": device_id,
        "cmd": "set_config",
        "success": bool(success),
        "message": message,
    }
    if config_applied is not None:
        ack["config"] = config_applied
    return ack
