"""Device simulation runtime wiring core modules together."""

from core.aggregation import Aggregator, should_report_by_exception
from core.buffer import StoreForwardBuffer
from core.config import normalize_config, apply_set_config
from core.espresso import EspressoMachine
from core.irregularities import IrregularityEngine
from core.scheduler import Scheduler
from core.schema import build_telemetry, build_cmd_ack


class DeviceRuntime:
    """Portable simulation loop for one espresso machine."""

    def __init__(self, config=None, seed=42):
        self.config = normalize_config(config)
        self.machine = EspressoMachine(seed=seed)
        self.irregularities = IrregularityEngine(self.config, seed=seed + 1)
        self.aggregator = Aggregator(list(self.machine.sample().keys()))
        self.scheduler = Scheduler(
            self.config["sample_interval_ms"],
            self.config["publish_interval_s"],
        )
        self.buffer = StoreForwardBuffer()
        self.seq = 0
        self._prev_faults = []
        self._prev_state = "idle"
        self.aggregator.reset_window()

    def apply_config(self, command):
        self.config = apply_set_config(self.config, command)
        self.irregularities.update_config(self.config)
        self.scheduler.update_intervals(
            self.config["sample_interval_ms"],
            self.config["publish_interval_s"],
        )
        return self.config

    def _collect_faults(self):
        faults = list(self.irregularities.active_faults())
        self.machine.active_faults = faults
        return faults

    def sample_once(self, timestamp, dt_seconds=None):
        dt = dt_seconds or self.config["sample_interval_ms"] / 1000.0
        raw = self.machine.sample(dt)
        processed = self.irregularities.apply(raw, dt)
        self.aggregator.add_sample(processed, timestamp)
        return processed

    def build_publish(self, timestamp, event="telemetry"):
        """Build a telemetry payload and reset the aggregation window."""
        faults = self._collect_faults()
        state = self.machine.state
        metrics = self.aggregator.build_metrics()
        rbe = should_report_by_exception(
            self._prev_faults, faults, self._prev_state, state, metrics
        )
        self.seq += 1
        evt = "exception" if rbe and event == "telemetry" else event
        payload = build_telemetry(
            device_id=self.config["device_id"],
            seq=self.seq,
            timestamp=timestamp,
            metrics=metrics,
            counters=self.machine.counters,
            state=state,
            active_faults=faults,
            window_start=self.aggregator.window_start,
            window_end=self.aggregator.window_end or timestamp,
            sample_count=self.aggregator.sample_count,
            event=evt,
        )
        self._prev_faults = list(faults)
        self._prev_state = state
        self.aggregator.reset_window(timestamp)
        return payload

    def tick(self, elapsed_ms, timestamp):
        """Advance scheduler; sample and maybe publish."""
        should_sample, should_publish = self.scheduler.tick(elapsed_ms)
        messages = []
        if should_sample:
            self.sample_once(timestamp)
        if should_publish:
            messages.append(self.build_publish(timestamp))
        else:
            faults = self._collect_faults()
            metrics = self.aggregator.build_metrics()
            if should_report_by_exception(
                self._prev_faults, faults, self._prev_state, self.machine.state, metrics
            ):
                messages.append(self.build_publish(timestamp))
        return messages

    def handle_command(self, command):
        try:
            cfg = self.apply_config(command)
            return build_cmd_ack(self.config["device_id"], True, "config applied", cfg)
        except Exception as e:
            return build_cmd_ack(self.config["device_id"], False, str(e))

    def enqueue_or_publish(self, payload, publish_fn):
        try:
            publish_fn(payload)
            for buffered in self.buffer.replay_all():
                publish_fn(buffered)
            return True
        except Exception:
            self.buffer.enqueue(payload)
            return False
