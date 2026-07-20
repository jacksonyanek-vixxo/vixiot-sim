"""Runtime configuration model for the espresso simulator."""

EQUIPMENT_TYPE = "super_automatic_espresso"
SCHEMA_VERSION = "1.0"

DEFAULT_EVENT_CATEGORIES = {
    "Machine Issue": {"enabled": True, "rate_multiplier": 1.0},
    "Operational Issue": {"enabled": True, "rate_multiplier": 1.0},
    "Cleaning": {"enabled": True, "rate_multiplier": 1.0},
    "Connectivity Events": {"enabled": True, "rate_multiplier": 1.0},
}

DEFAULT_EVENTS = {
    "enabled": True,
    "global_rate_multiplier": 1.0,
    "categories": DEFAULT_EVENT_CATEGORIES,
    "inject": [],
}

DEFAULT_IRREGULARITIES = {
    "scaling": {"enabled": False, "mtbf_hours": 200, "severity": 0.5},
    "grinder_wear": {"enabled": False, "severity": 0.3},
    "pump_degradation": {"enabled": False, "severity": 0.4},
    "clogged_group": {"enabled": False, "severity": 0.6},
    "heater_degradation": {"enabled": False, "severity": 0.5},
    "spike": {"enabled": False, "rate_per_hour": 2, "severity": 0.5},
    "drift": {"enabled": False, "rate_per_hour": 1, "severity": 0.3},
    "stuck": {"enabled": False, "rate_per_hour": 0.5, "severity": 0.5},
    "dropout": {"enabled": False, "rate_per_hour": 1, "severity": 1.0},
    "out_of_range": {"enabled": False, "rate_per_hour": 0.5, "severity": 0.8},
    "noise": {"enabled": False, "rate_per_hour": 5, "severity": 0.2},
}

DEFAULT_CONFIG = {
    "device_id": "espresso-001",
    "sample_interval_ms": 1000,
    "publish_interval_s": 30,
    "irregularities": DEFAULT_IRREGULARITIES,
    "events": DEFAULT_EVENTS,
}


def _deep_merge(base, override):
    result = {}
    for key, value in base.items():
        if key in override and isinstance(value, dict) and isinstance(override[key], dict):
            result[key] = _deep_merge(value, override[key])
        elif key in override:
            result[key] = override[key]
        else:
            result[key] = value
    for key, value in override.items():
        if key not in result:
            result[key] = value
    return result


def normalize_config(raw=None):
    """Merge user overrides with defaults."""
    if raw is None:
        raw = {}
    merged = _deep_merge(DEFAULT_CONFIG, raw)
    merged["sample_interval_ms"] = max(100, int(merged.get("sample_interval_ms", 1000)))
    merged["publish_interval_s"] = max(1, int(merged.get("publish_interval_s", 30)))
    merged["device_id"] = str(merged.get("device_id", DEFAULT_CONFIG["device_id"]))
    return merged


def apply_set_config(current, command):
    """Apply a set_config downlink command onto current config."""
    if command.get("cmd") != "set_config":
        raise ValueError("unsupported command: %s" % command.get("cmd"))
    patch = {}
    for key in ("sample_interval_ms", "publish_interval_s", "device_id"):
        if key in command:
            patch[key] = command[key]
    if "irregularities" in command:
        patch["irregularities"] = command["irregularities"]
    if "events" in command:
        patch["events"] = command["events"]
    return normalize_config(_deep_merge(current, patch))
