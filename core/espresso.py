"""Schaerer-style super-automatic espresso machine profile."""

try:
    import random
except ImportError:
    random = None

EQUIPMENT_TYPE = "super_automatic_espresso"

MACHINE_STATES = ("idle", "brewing", "steaming", "cleaning", "fault")

METRIC_SPECS = {
    "brew_boiler_temp": {"unit": "degC", "healthy": (91.0, 94.0), "idle": 92.5, "brewing": 93.0},
    "steam_boiler_temp": {"unit": "degC", "healthy": (125.0, 135.0), "idle": 128.0, "steaming": 132.0},
    "brew_pressure": {"unit": "bar", "healthy": (8.5, 9.5), "idle": 0.2, "brewing": 9.1},
    "pump_current": {"unit": "A", "healthy": (0.5, 1.8), "idle": 0.1, "brewing": 1.2},
    "grinder_current": {"unit": "A", "healthy": (1.5, 3.5), "idle": 0.0, "brewing": 2.8},
    "water_flow": {"unit": "ml_s", "healthy": (0.0, 12.0), "idle": 0.0, "brewing": 8.5},
    "ambient_temp": {"unit": "degC", "healthy": (18.0, 28.0), "idle": 22.0, "brewing": 22.0},
}

PM_BANDS = {
    "descale_due_shots": 500,
    "burr_replace_shots": 15000,
    "pm_service_hours": 2000,
}


class EspressoMachine:
    """Generates healthy baseline signals and tracks counters/state."""

    def __init__(self, seed=42):
        self._rng = random.Random(seed) if random else None
        self._tick = 0
        self._state = "idle"
        self._state_ticks = 0
        self._state_duration = 20
        self.counters = {
            "total_shots": 10432,
            "shots_since_descale": 210,
            "operating_hours": 512.3,
        }
        self.active_faults = []

    def _rand(self):
        if self._rng:
            return self._rng.random()
        return 0.5

    def _noise(self, scale=0.05):
        return (self._rand() - 0.5) * 2 * scale

    def _advance_state(self):
        self._state_ticks += 1
        if self._state_ticks >= self._state_duration:
            self._state_ticks = 0
            if self._state == "idle":
                roll = self._rand()
                if roll < 0.55:
                    self._state = "brewing"
                    self._state_duration = 8
                    self.counters["total_shots"] += 1
                    self.counters["shots_since_descale"] += 1
                elif roll < 0.70:
                    self._state = "steaming"
                    self._state_duration = 6
                elif roll < 0.78:
                    self._state = "cleaning"
                    self._state_duration = 12
                else:
                    self._state_duration = 15 + int(self._rand() * 20)
            elif self._state in ("brewing", "steaming", "cleaning"):
                self._state = "idle"
                self._state_duration = 10 + int(self._rand() * 25)
            elif self._state == "fault":
                self._state = "idle"
                self._state_duration = 20

    def sample(self, dt_seconds=1.0):
        """Produce one raw sample dict keyed by metric name."""
        self._tick += 1
        self.counters["operating_hours"] += dt_seconds / 3600.0
        self._advance_state()

        if self.active_faults:
            self._state = "fault"

        samples = {}
        for name, spec in METRIC_SPECS.items():
            base = spec.get(self._state, spec["idle"])
            if self._state == "idle" and name in ("brew_pressure", "pump_current", "grinder_current", "water_flow"):
                value = max(0.0, base + self._noise(0.02))
            else:
                value = base + self._noise(0.15 if name.endswith("_temp") else 0.08)
            samples[name] = {
                "value": round(value, 2),
                "unit": spec["unit"],
                "quality": "good",
            }
        return samples

    @property
    def state(self):
        return self._state

    def set_state(self, state):
        if state in MACHINE_STATES:
            self._state = state

    def pm_advisories(self):
        """Return PM-related advisory fault names based on counters."""
        advisories = []
        if self.counters["shots_since_descale"] >= PM_BANDS["descale_due_shots"]:
            advisories.append("descale_due")
        if self.counters["total_shots"] >= PM_BANDS["burr_replace_shots"]:
            advisories.append("burr_replace_due")
        if self.counters["operating_hours"] >= PM_BANDS["pm_service_hours"]:
            advisories.append("pm_service_due")
        return advisories

    def is_healthy_value(self, metric, value):
        spec = METRIC_SPECS.get(metric)
        if not spec:
            return True
        lo, hi = spec["healthy"]
        return lo <= value <= hi
