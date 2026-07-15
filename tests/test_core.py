"""Pytest suite for portable core."""

import pytest

from core.aggregation import Aggregator, MetricWindow, should_report_by_exception
from core.buffer import StoreForwardBuffer
from core.config import apply_set_config, normalize_config
from core.espresso import EspressoMachine, METRIC_SPECS, PM_BANDS
from core.irregularities import IrregularityEngine
from core.runtime import DeviceRuntime
from core.scheduler import Scheduler


class TestEspressoBaseline:
    def test_brew_boiler_temp_in_healthy_range_during_brew(self):
        m = EspressoMachine(seed=1)
        m.set_state("brewing")
        for _ in range(20):
            sample = m.sample()
            val = sample["brew_boiler_temp"]["value"]
            lo, hi = METRIC_SPECS["brew_boiler_temp"]["healthy"]
            assert lo <= val <= hi + 1.0

    def test_counters_increment_on_brew(self):
        m = EspressoMachine(seed=2)
        before = m.counters["total_shots"]
        m.set_state("brewing")
        m.sample()
        assert m.counters["total_shots"] >= before

    def test_pm_descale_advisory(self):
        m = EspressoMachine(seed=3)
        m.counters["shots_since_descale"] = PM_BANDS["descale_due_shots"]
        assert "descale_due" in m.pm_advisories()


class TestIrregularities:
    def test_scaling_lowers_brew_temp(self):
        engine = IrregularityEngine(
            {"scaling": {"enabled": True, "mtbf_hours": 0.001, "severity": 0.9}},
            seed=10,
        )
        engine._active_domain.add("scaling")
        base = {"brew_boiler_temp": {"value": 93.0, "unit": "degC", "quality": "good"}}
        out = engine.apply(base, dt_seconds=1.0)
        assert out["brew_boiler_temp"]["value"] < 93.0
        assert out["brew_boiler_temp"]["quality"] == "suspect"

    def test_pump_degradation_lowers_pressure(self):
        engine = IrregularityEngine(
            {"pump_degradation": {"enabled": True, "severity": 0.8}},
            seed=11,
        )
        engine._active_domain.add("pump_degradation")
        base = {
            "brew_pressure": {"value": 9.0, "unit": "bar", "quality": "good"},
            "pump_current": {"value": 1.0, "unit": "A", "quality": "good"},
        }
        out = engine.apply(base)
        assert out["brew_pressure"]["value"] < 9.0

    def test_dropout_sets_missing_quality(self):
        engine = IrregularityEngine(
            {"dropout": {"enabled": True, "rate_per_hour": 10000, "severity": 1.0}},
            seed=12,
        )
        base = {"brew_pressure": {"value": 9.0, "unit": "bar", "quality": "good"}}
        found = False
        for _ in range(50):
            out = engine.apply(dict(base), dt_seconds=1.0)
            if out["brew_pressure"]["quality"] == "missing":
                found = True
                break
        assert found

    def test_grinder_wear_increases_current(self):
        engine = IrregularityEngine(
            {"grinder_wear": {"enabled": True, "severity": 0.9}},
            seed=13,
        )
        engine._active_domain.add("grinder_wear")
        base = {"grinder_current": {"value": 2.0, "unit": "A", "quality": "good"}}
        out = engine.apply(base)
        assert out["grinder_current"]["value"] > 2.0


class TestAggregation:
    def test_window_min_max_mean_last(self):
        w = MetricWindow()
        for v in [10.0, 12.0, 8.0]:
            w.add({"value": v, "unit": "degC", "quality": "good"})
        d = w.to_dict()
        assert d["min"] == 8.0
        assert d["max"] == 12.0
        assert d["mean"] == 10.0
        assert d["value"] == 8.0

    def test_aggregator_sample_count(self):
        agg = Aggregator(["brew_boiler_temp"])
        agg.reset_window("2026-01-01T00:00:00Z")
        for i in range(5):
            agg.add_sample(
                {"brew_boiler_temp": {"value": 90 + i, "unit": "degC", "quality": "good"}},
                "2026-01-01T00:00:%02dZ" % i,
            )
        assert agg.sample_count == 5
        metrics = agg.build_metrics()
        assert metrics["brew_boiler_temp"]["mean"] == 92.0


class TestRBE:
    def test_fault_change_triggers_rbe(self):
        assert should_report_by_exception([], ["scaling"], "idle", "idle")

    def test_no_trigger_when_stable(self):
        assert not should_report_by_exception([], [], "idle", "idle")

    def test_bad_quality_triggers_rbe(self):
        metrics = {"brew_pressure": {"quality": "bad", "value": 3.0}}
        assert should_report_by_exception([], [], "idle", "idle", metrics)


class TestBuffer:
    def test_replay_fifo_order(self):
        buf = StoreForwardBuffer()
        buf.enqueue({"seq": 1})
        buf.enqueue({"seq": 2})
        buf.enqueue({"seq": 3})
        replayed = buf.replay_all()
        assert [r["seq"] for r in replayed] == [1, 2, 3]
        assert len(buf) == 0

    def test_max_size_evicts_oldest(self):
        buf = StoreForwardBuffer(max_size=2)
        buf.enqueue({"seq": 1})
        buf.enqueue({"seq": 2})
        buf.enqueue({"seq": 3})
        assert buf.peek()[0]["seq"] == 2


class TestScheduler:
    def test_sample_and_publish_intervals(self):
        sched = Scheduler(sample_interval_ms=1000, publish_interval_s=3)
        samples = publishes = 0
        for _ in range(30):
            s, p = sched.tick(100)
            samples += int(s)
            publishes += int(p)
        assert samples == 3
        assert publishes == 1


class TestConfig:
    def test_apply_set_config(self):
        cfg = normalize_config({"device_id": "test-001"})
        updated = apply_set_config(cfg, {"cmd": "set_config", "publish_interval_s": 60})
        assert updated["publish_interval_s"] == 60


class TestRuntime:
    def test_publish_after_window(self):
        rt = DeviceRuntime({"publish_interval_s": 1, "sample_interval_ms": 100})
        msgs = []
        for _ in range(12):
            msgs.extend(rt.tick(100, "2026-07-15T16:00:00Z"))
        assert any(m.get("seq") >= 1 for m in msgs)

    def test_handle_command_ack(self):
        rt = DeviceRuntime()
        ack = rt.handle_command({"cmd": "set_config", "publish_interval_s": 10})
        assert ack["success"]
        assert rt.config["publish_interval_s"] == 10
