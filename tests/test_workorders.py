"""Tests for sink work-order manager."""

from sink.workorders import WorkOrderManager


def _event_payload(number, name, severity, transition, module="CoffeeModule1", seq=1):
    return {
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "seq": seq,
        "event": {
            "number": number,
            "name": name,
            "severity": severity,
            "category": "Machine Issue",
            "module": module,
            "source": module,
            "stateful": True,
            "transition": transition,
        },
    }


def test_opens_one_wo_per_fault(tmp_path):
    wo_path = tmp_path / "wo.jsonl"
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=wo_path)

    payload = {
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "seq": 10,
        "active_faults": ["scaling"],
    }
    mgr.process_telemetry(payload)
    mgr.process_telemetry(payload)

    opens = [e for e in emitted if e["action"] == "created"]
    assert len(opens) == 1
    assert opens[0]["fault"] == "scaling"


def test_closes_wo_when_fault_clears(tmp_path):
    wo_path = tmp_path / "wo.jsonl"
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=wo_path)

    mgr.process_telemetry({
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "seq": 1,
        "active_faults": ["scaling"],
    })
    mgr.process_telemetry({
        "device_id": "espresso-001",
        "equipment_type": "super_automatic_espresso",
        "seq": 2,
        "active_faults": [],
    })

    closes = [e for e in emitted if e["action"] == "closed"]
    assert len(closes) == 1
    assert closes[0]["status"] == "closed"


def test_opens_one_wo_per_event_module(tmp_path):
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=tmp_path / "wo.jsonl")

    mgr.process_event(_event_payload(56, "SteamOutletNotAvailable", "Error", "raised", "SteamManager"))
    mgr.process_event(_event_payload(56, "SteamOutletNotAvailable", "Error", "raised", "SteamManager"))

    opens = [e for e in emitted if e["action"] == "created"]
    assert len(opens) == 1
    assert opens[0]["module"] == "SteamManager"
    assert opens[0]["source"] == "event"


def test_closes_event_wo_on_clear(tmp_path):
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=tmp_path / "wo.jsonl")

    mgr.process_event(_event_payload(56, "SteamOutletNotAvailable", "Error", "raised", "SteamManager", seq=1))
    mgr.process_event(_event_payload(55, "SteamOutletAvailable", "Info", "cleared", "SteamManager", seq=2))

    closes = [e for e in emitted if e["action"] == "closed"]
    assert len(closes) == 1
    assert closes[0]["event_name"] == "SteamOutletNotAvailable"


def test_separate_modules_get_separate_event_wos(tmp_path):
    emitted = []
    mgr = WorkOrderManager(publish_fn=lambda r: emitted.append(r), persist_path=tmp_path / "wo.jsonl")

    mgr.process_event(_event_payload(19, "GroundsDrawerFull", "Error", "raised", "GroundsDrawer1"))
    mgr.process_event(_event_payload(19, "GroundsDrawerFull", "Error", "raised", "GroundsDrawer2"))

    opens = [e for e in emitted if e["action"] == "created"]
    assert len(opens) == 2
    assert {item["module"] for item in opens} == {"GroundsDrawer1", "GroundsDrawer2"}
