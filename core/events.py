"""Mastrena-style discrete event generation engine."""

from core.espresso import PM_BANDS
from core.events_catalog import (
    CATALOG,
    FAULT_EVENT_MAP,
    PAIRS,
    STOCHASTIC_INFO,
    clear_number,
    is_stateful,
    lookup,
    pairing_group,
    resolve_module,
)
from core.rng import SeededRng

CLEANING_RECOMMENDED_RATIO = 0.85
CLEANING_REQUIRED_RATIO = 1.0
SERVICE_RECOMMENDED_RATIO = 0.9
SERVICE_REQUIRED_RATIO = 1.0
GROUNDS_FULL_SHOTS = 80


class EventEngine:
    """Generate catalog events from machine state, counters, and faults."""

    def __init__(self, config=None, seed=77):
        self._rng = SeededRng(seed)
        self._config = {}
        self._active = {}
        self._prev_state = "idle"
        self._prev_faults = set()
        self._grounds_shots = 0
        self._cleaning_level = "ok"
        self._service_level = "ok"
        self._pending = []
        self.update_config(config or {})

    def update_config(self, config):
        if isinstance(config, dict):
            self._config = config.get("events", config)

    def _rand(self):
        return self._rng.random() if self._rng else 0.5

    def _events_cfg(self):
        return self._config if isinstance(self._config, dict) else {}

    def enabled(self):
        return self._events_cfg().get("enabled", True)

    def _category_enabled(self, category):
        cfg = self._events_cfg()
        categories = cfg.get("categories", {})
        entry = categories.get(category, {})
        return entry.get("enabled", True)

    def _category_rate(self, category):
        cfg = self._events_cfg()
        categories = cfg.get("categories", {})
        entry = categories.get(category, {})
        multiplier = float(entry.get("rate_multiplier", 1.0))
        global_rate = float(cfg.get("global_rate_multiplier", 1.0))
        return max(0.0, multiplier * global_rate)

    def _rate_trigger(self, rate_per_hour, dt_hours):
        if rate_per_hour <= 0:
            return False
        p = min(1.0, rate_per_hour * dt_hours)
        return self._rand() < p

    def _make_occurrence(self, number, transition, module=None, source=None):
        entry = lookup(number)
        if not entry:
            return None
        name, severity, category = entry
        module = module or resolve_module(number, self._rng)
        source = source or module
        stateful = is_stateful(number)
        return {
            "number": number,
            "name": name,
            "severity": severity,
            "category": category,
            "module": module,
            "source": source,
            "stateful": stateful,
            "transition": transition,
        }

    def _emit(self, number, transition, module=None, source=None):
        occ = self._make_occurrence(number, transition, module, source)
        if occ:
            self._pending.append(occ)
        return occ

    def _raise_stateful(self, number, module=None, source=None):
        group = pairing_group(number)
        key = (group, module or resolve_module(number, self._rng))
        if key in self._active:
            return None
        occ = self._emit(number, "raised", module=key[1], source=source)
        if occ:
            self._active[key] = number
        return occ

    def _clear_stateful(self, number, module=None, source=None):
        group = pairing_group(number)
        module = module or resolve_module(number, self._rng)
        key = (group, module)
        raise_num = self._active.pop(key, None)
        clear_num = clear_number(raise_num) if raise_num else number
        if clear_num is None:
            clear_num = number
        return self._emit(clear_num, "cleared", module=module, source=source)

    def _clear_by_raise(self, raise_number, module=None, source=None):
        group = pairing_group(raise_number)
        module = module or resolve_module(raise_number, self._rng)
        key = (group, module)
        if key not in self._active:
            return None
        self._active.pop(key, None)
        clear_num = clear_number(raise_number) or raise_number
        return self._emit(clear_num, "cleared", module=module, source=source)

    def inject(self, number, transition="raised", module=None, source=None):
        if transition == "raised" and number in PAIRS:
            return self._raise_stateful(number, module, source)
        if transition == "cleared":
            return self._clear_stateful(number, module, source)
        return self._emit(number, "momentary", module, source)

    def _process_inject(self):
        cfg = self._events_cfg()
        for item in cfg.get("inject", []) or []:
            if isinstance(item, dict):
                number = int(item.get("number"))
                transition = item.get("transition", "raised")
                module = item.get("module")
                source = item.get("source")
            else:
                number = int(item)
                transition = "raised"
                module = None
                source = None
            self.inject(number, transition, module, source)

    def _process_state_transitions(self, state):
        prev = self._prev_state
        if state == prev:
            return
        if state == "brewing" and prev == "idle":
            self._emit(7, "momentary")
            self._grounds_shots += 1
            if self._grounds_shots >= GROUNDS_FULL_SHOTS:
                drawer = resolve_module(19, self._rng)
                self._raise_stateful(19, module=drawer)
        elif state == "steaming" and prev == "idle":
            self._raise_stateful(56, module="SteamManager", source="SteamManager")
        elif state == "idle" and prev == "steaming":
            self._clear_by_raise(56, module="SteamManager", source="SteamManager")
        elif state == "cleaning":
            self._emit(136, "momentary", module="CleaningDispatcher")
            self._emit(6, "momentary", module="BoilerController")
        elif state == "idle" and prev == "cleaning":
            self._emit(10006, "momentary", module="CleaningDispatcher")
            drawer = resolve_module(19, self._rng)
            if self._grounds_shots >= GROUNDS_FULL_SHOTS:
                self._clear_by_raise(19, module=drawer)
                self._grounds_shots = 0
        self._prev_state = state

    def _process_counters(self, counters):
        shots = counters.get("shots_since_descale", 0)
        hours = counters.get("operating_hours", 0.0)
        descale_due = PM_BANDS["descale_due_shots"]
        pm_hours = PM_BANDS["pm_service_hours"]

        cleaning_level = "ok"
        if shots >= descale_due * CLEANING_REQUIRED_RATIO:
            cleaning_level = "required"
        elif shots >= descale_due * CLEANING_RECOMMENDED_RATIO:
            cleaning_level = "recommended"

        service_level = "ok"
        if hours >= pm_hours * SERVICE_REQUIRED_RATIO:
            service_level = "required"
        elif hours >= pm_hours * SERVICE_RECOMMENDED_RATIO:
            service_level = "recommended"

        if cleaning_level != self._cleaning_level:
            if self._cleaning_level == "required":
                self._clear_by_raise(28, module="CleaningDispatcher")
            elif self._cleaning_level == "recommended":
                self._clear_by_raise(27, module="CleaningDispatcher")
            if cleaning_level == "recommended":
                self._raise_stateful(27, module="CleaningDispatcher")
            elif cleaning_level == "required":
                self._raise_stateful(28, module="CleaningDispatcher")
            self._cleaning_level = cleaning_level

        if service_level != self._service_level:
            if self._service_level == "required":
                self._clear_by_raise(47, module="OperationProcessor")
            elif self._service_level == "recommended":
                self._clear_by_raise(46, module="OperationProcessor")
            if service_level == "recommended":
                self._raise_stateful(46, module="OperationProcessor")
            elif service_level == "required":
                self._raise_stateful(47, module="OperationProcessor")
            self._service_level = service_level

    def _process_faults(self, active_faults):
        faults = set(active_faults or [])
        for fault, number in FAULT_EVENT_MAP.items():
            module = resolve_module(number, self._rng)
            if fault in faults and fault not in self._prev_faults:
                self._raise_stateful(number, module=module, source=module)
            elif fault not in faults and fault in self._prev_faults:
                self._clear_by_raise(number, module=module, source=module)
        self._prev_faults = set(faults)

    def _process_stochastic(self, dt_hours):
        base_rates = {
            "Machine Issue": 0.5,
            "Operational Issue": 0.2,
            "Cleaning": 0.1,
        }
        for category, numbers in STOCHASTIC_INFO.items():
            if not numbers or not self._category_enabled(category):
                continue
            rate = base_rates.get(category, 0.1) * self._category_rate(category)
            if not self._rate_trigger(rate, dt_hours):
                continue
            number = numbers[int(self._rand() * len(numbers)) % len(numbers)]
            self._emit(number, "momentary")

    def step(self, dt_seconds, state, counters, active_faults):
        """Advance simulation and return new event occurrences."""
        self._pending = []
        if not self.enabled():
            self._prev_state = state
            self._prev_faults = set(active_faults or [])
            return []

        dt_hours = dt_seconds / 3600.0
        self._process_inject()
        self._process_state_transitions(state)
        self._process_counters(counters or {})
        self._process_faults(active_faults)
        self._process_stochastic(dt_hours)
        pending = list(self._pending)
        self._pending = []
        return pending

    def connectivity_event(self, connected):
        number = 20001 if connected else 20002
        transition = "cleared" if connected else "raised"
        if connected:
            return self._emit(number, "momentary", module="StatusManager", source="StatusManager")
        return self._raise_stateful(number, module="StatusManager", source="StatusManager")
