"""Windowed aggregation and report-by-exception logic."""


class MetricWindow:
    """Accumulates min/max/mean/last for one metric over a window."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.count = 0
        self.last = None
        self.min = None
        self.max = None
        self.sum = 0.0
        self.unit = None
        self.quality = "good"

    def add(self, sample):
        value = sample.get("value")
        if value is None or sample.get("quality") == "missing":
            if self.count == 0:
                self.quality = "missing"
            return
        self.count += 1
        self.last = value
        self.unit = sample.get("unit", self.unit)
        q = sample.get("quality", "good")
        if q != "good":
            self.quality = q
        self.min = value if self.min is None else min(self.min, value)
        self.max = value if self.max is None else max(self.max, value)
        self.sum += value

    def to_dict(self):
        if self.count == 0:
            return {"quality": self.quality or "missing"}
        d = {
            "value": self.last,
            "unit": self.unit,
            "min": round(self.min, 2),
            "max": round(self.max, 2),
            "mean": round(self.sum / self.count, 2),
            "quality": self.quality,
        }
        return d


class Aggregator:
    """Collects samples into per-metric windows."""

    def __init__(self, metric_names=None):
        self._metrics = metric_names or []
        self._windows = {}
        self.window_start = None
        self.window_end = None
        self.sample_count = 0

    def reset_window(self, start_ts=None):
        self._windows = {name: MetricWindow() for name in self._metrics}
        self.window_start = start_ts
        self.window_end = start_ts
        self.sample_count = 0

    def ensure_metrics(self, sample_keys):
        for key in sample_keys:
            if key not in self._windows:
                self._windows[key] = MetricWindow()
                if key not in self._metrics:
                    self._metrics.append(key)

    def add_sample(self, sample_dict, timestamp):
        self.ensure_metrics(sample_dict.keys())
        if self.window_start is None:
            self.window_start = timestamp
        self.window_end = timestamp
        self.sample_count += 1
        for name, reading in sample_dict.items():
            self._windows[name].add(reading)

    def build_metrics(self):
        return {name: w.to_dict() for name, w in self._windows.items()}


def should_report_by_exception(prev_faults, curr_faults, prev_state, curr_state, metrics=None):
    """Return True if an immediate publish is warranted."""
    prev_set = set(prev_faults or [])
    curr_set = set(curr_faults or [])
    if prev_set != curr_set:
        return True
    if prev_state != curr_state and curr_state == "fault":
        return True
    if metrics:
        for reading in metrics.values():
            if reading.get("quality") in ("bad", "missing"):
                return True
    return False
