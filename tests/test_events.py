"""Tests for Mastrena-style event catalog and engine."""

from core.config import apply_set_config, normalize_config
from core.events import EventEngine
from core.events_catalog import CATALOG, PAIRS, SEVERITY_RANK, clear_number, is_stateful, lookup, pairing_group
from core.runtime import DeviceRuntime
from core.schema import build_event


def test_catalog_has_73_events():
    assert len(CATALOG) == 73


def test_catalog_severities_are_valid():
    for number, (_name, severity, _category) in CATALOG.items():
        assert severity in SEVERITY_RANK


def test_pairs_reference_valid_events():
    for raise_num, clear_num in PAIRS.items():
        assert raise_num in CATALOG
        assert clear_num in CATALOG


def test_pairing_group_is_stable():
    assert pairing_group(9) == 8
    assert pairing_group(8) == 8


def test_stateful_detection():
    assert is_stateful(9)
    assert is_stateful(8)
    assert not is_stateful(7)


def test_engine_inject_raise_and_clear():
    engine = EventEngine({"enabled": True, "inject": [{"number": 56, "transition": "raised", "module": "SteamManager"}]})
    raised = engine.step(1.0, "idle", {}, [])
    assert len(raised) == 1
    assert raised[0]["number"] == 56
    assert raised[0]["transition"] == "raised"

    cleared = engine.inject(55, "cleared", module="SteamManager")
    assert cleared["transition"] == "cleared"


def test_engine_respects_disabled_config():
    engine = EventEngine({"enabled": False, "inject": [{"number": 56}]})
    assert engine.step(1.0, "steaming", {}, []) == []


def test_fault_triggers_and_clears_event():
    engine = EventEngine({"enabled": True}, seed=1)
    raised = engine.step(1.0, "idle", {}, ["pump_degradation"])
    assert any(item["number"] == 34 for item in raised)
    cleared = engine.step(1.0, "idle", {}, [])
    assert any(item["number"] == 55 and item["transition"] == "cleared" for item in cleared)


def test_apply_set_config_merges_events():
    cfg = normalize_config({})
    updated = apply_set_config(
        cfg,
        {
            "cmd": "set_config",
            "events": {"enabled": False, "global_rate_multiplier": 2.0},
        },
    )
    assert updated["events"]["enabled"] is False
    assert updated["events"]["global_rate_multiplier"] == 2.0


def test_runtime_emits_event_payloads():
    rt = DeviceRuntime({"sample_interval_ms": 100, "publish_interval_s": 30, "events": {"enabled": True, "inject": [{"number": 20001}]}})
    _telemetry, events = rt.tick(100, "2026-07-15T16:00:00Z")
    assert events
    payload = events[0]
    assert payload["device_id"] == rt.config["device_id"]
    assert payload["event"]["number"] == 20001


def test_build_event_shape():
    payload = build_event(
        "espresso-001",
        1,
        "2026-07-15T16:00:00Z",
        {
            "number": 9,
            "name": "StatusManagerError",
            "severity": "Error",
            "category": "Machine Issue",
            "module": "StatusManager",
            "source": "StatusManager",
            "stateful": True,
            "transition": "raised",
        },
    )
    assert payload["event"]["transition"] == "raised"
    assert clear_number(9) == 8
