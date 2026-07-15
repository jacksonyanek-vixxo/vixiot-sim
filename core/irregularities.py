"""Layered irregularity engine: domain failures + generic signal anomalies."""

try:
    import random
except ImportError:
    random = None

DOMAIN_FAULTS = (
    "scaling",
    "grinder_wear",
    "pump_degradation",
    "clogged_group",
    "heater_degradation",
)

GENERIC_ANOMALIES = (
    "spike",
    "drift",
    "stuck",
    "dropout",
    "out_of_range",
    "noise",
)


class IrregularityEngine:
    """Apply configured failure patterns and signal anomalies to samples."""

    def __init__(self, config=None, seed=99):
        self._rng = random.Random(seed) if random else None
        self._config = {}
        self._active_domain = set()
        self._drift_offsets = {}
        self._stuck_values = {}
        self._hours_elapsed = 0.0
        self._sample_count = 0
        self.update_config(config or {})

    def update_config(self, config):
        self._config = config.get("irregularities", config) if isinstance(config, dict) else {}

    def _rand(self):
        return self._rng.random() if self._rng else 0.5

    def _cfg(self, name):
        return self._config.get(name, {})

    def _rate_trigger(self, rate_per_hour, dt_hours):
        if rate_per_hour <= 0:
            return False
        p = 1.0 - pow(1.0 - min(rate_per_hour * dt_hours, 1.0), 1.0)
        return self._rand() < p

    def _maybe_start_domain_fault(self, name, dt_hours):
        cfg = self._cfg(name)
        if not cfg.get("enabled"):
            return
        if name in self._active_domain:
            return
        mtbf = cfg.get("mtbf_hours", 500)
        severity = cfg.get("severity", 0.5)
        if mtbf <= 0:
            return
        p = dt_hours / mtbf * (0.5 + severity)
        if self._rand() < p:
            self._active_domain.add(name)

    def _maybe_clear_domain_fault(self, name):
        cfg = self._cfg(name)
        if name not in self._active_domain:
            return
        severity = cfg.get("severity", 0.5)
        if self._rand() < 0.002 * (1.0 - severity):
            self._active_domain.discard(name)

    def tick(self, dt_seconds=1.0):
        dt_hours = dt_seconds / 3600.0
        self._hours_elapsed += dt_hours
        self._sample_count += 1
        for fault in DOMAIN_FAULTS:
            self._maybe_start_domain_fault(fault, dt_hours)
            self._maybe_clear_domain_fault(fault)

    def active_faults(self):
        return sorted(self._active_domain)

    def _apply_domain(self, samples):
        result = {k: dict(v) for k, v in samples.items()}

        if "scaling" in self._active_domain:
            sev = self._cfg("scaling").get("severity", 0.5)
            if "brew_boiler_temp" in result:
                result["brew_boiler_temp"]["value"] -= 2.0 + 4.0 * sev
                result["brew_boiler_temp"]["quality"] = "suspect"
            if "brew_pressure" in result:
                result["brew_pressure"]["value"] -= 0.5 + sev
                result["brew_pressure"]["quality"] = "suspect"

        if "grinder_wear" in self._active_domain:
            sev = self._cfg("grinder_wear").get("severity", 0.3)
            if "grinder_current" in result:
                result["grinder_current"]["value"] += 0.8 + 1.5 * sev
                result["grinder_current"]["quality"] = "suspect"

        if "pump_degradation" in self._active_domain:
            sev = self._cfg("pump_degradation").get("severity", 0.4)
            if "pump_current" in result:
                result["pump_current"]["value"] += 0.4 + 1.2 * sev
            if "brew_pressure" in result:
                result["brew_pressure"]["value"] -= 1.0 + 2.0 * sev
                result["brew_pressure"]["quality"] = "bad"

        if "clogged_group" in self._active_domain:
            sev = self._cfg("clogged_group").get("severity", 0.6)
            if "water_flow" in result:
                result["water_flow"]["value"] *= max(0.1, 1.0 - 0.6 * sev)
            if "brew_pressure" in result:
                result["brew_pressure"]["value"] += 1.5 + 2.0 * sev
                result["brew_pressure"]["quality"] = "bad"

        if "heater_degradation" in self._active_domain:
            sev = self._cfg("heater_degradation").get("severity", 0.5)
            for key in ("brew_boiler_temp", "steam_boiler_temp"):
                if key in result:
                    result[key]["value"] -= 3.0 + 5.0 * sev
                    result[key]["quality"] = "bad"

        return result

    def _pick_channel(self, samples):
        keys = list(samples.keys())
        if not keys:
            return None
        return keys[int(self._rand() * len(keys)) % len(keys)]

    def _apply_generic(self, samples, dt_seconds):
        dt_hours = dt_seconds / 3600.0
        result = {k: dict(v) for k, v in samples.items()}

        for name in GENERIC_ANOMALIES:
            cfg = self._cfg(name)
            if not cfg.get("enabled"):
                continue
            rate = cfg.get("rate_per_hour", 1)
            severity = cfg.get("severity", 0.5)
            if not self._rate_trigger(rate, dt_hours):
                continue

            channel = self._pick_channel(result)
            if not channel:
                continue
            entry = result[channel]
            val = entry["value"]

            if name == "spike":
                entry["value"] = val + (10.0 * severity if self._rand() > 0.5 else -10.0 * severity)
                entry["quality"] = "suspect"
            elif name == "drift":
                offset = self._drift_offsets.get(channel, 0.0)
                offset += (self._rand() - 0.4) * severity * 0.5
                self._drift_offsets[channel] = offset
                entry["value"] = val + offset
                entry["quality"] = "suspect"
            elif name == "stuck":
                if channel not in self._stuck_values:
                    self._stuck_values[channel] = val
                entry["value"] = self._stuck_values[channel]
                entry["quality"] = "bad"
            elif name == "dropout":
                entry["quality"] = "missing"
            elif name == "out_of_range":
                entry["value"] = val + 50.0 * severity
                entry["quality"] = "bad"
            elif name == "noise":
                entry["value"] = val + (self._rand() - 0.5) * 4.0 * severity
                entry["quality"] = "suspect"

            result[channel] = entry

        return result

    def apply(self, samples, dt_seconds=1.0):
        self.tick(dt_seconds)
        out = self._apply_domain(samples)
        out = self._apply_generic(out, dt_seconds)
        return out
